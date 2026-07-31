#!/usr/bin/env python3
"""Bounded executable challenge for the proposed ADR-004 authorization design.

This is synthetic, pre-ratification architecture evidence. It is not a wire
implementation, interoperability result, release gate, certification, safety
case, or production-security claim.

The probe deliberately uses independent authority stores. Each store publishes
one immutable snapshot pointer containing its selected state, canonical object
bytes, exact signed receipt bytes, and transition history. Candidate data stays
private until one pointer replacement makes the complete transaction visible.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar

from bounded_canonical import (
    CanonicalLimits,
    FrozenMap,
    FrozenTypeRegistry,
    freeze_owned,
    validate_immutable,
)
from bounded_canonical import (
    canonical_bytes as _bounded_canonical_bytes,
)
from observer_read_capture_bridge import (
    HISTORY_CONTENT_DOMAIN,
    LIVE_ROUTE_DOMAIN,
    NO_FUTURE_AUTHORITY,
    READ_ROUTE_CLASS_SHAPES,
    BridgeValidationError,
    CanonicalObserverReadScope,
    ExpectedCommittedObserverReadOutboxStateCut,
    ExpectedDispatchDestinationCut,
    ExpectedGrantCurrentnessStateCut,
    ExpectedObserverReadAuthorizationCut,
    ExpectedQualifiedDeadlineMappingStateCut,
    ObserverBoundaryReadScopeMembership,
    ObserverReadReleaseCAS,
    QualifiedDecisionDeadlineMapping,
    SealedObserverReadAuthorizationDecision,
    SyntheticAuthenticatedDispatchContext,
    SyntheticAuthenticatedGrantCurrentnessEvidence,
    SyntheticCommittedObserverReadOutboxArtifact,
    SyntheticObserverReadOutboxCommitReceipt,
    SyntheticValidatedObserverReadReleaseCASReceipt,
    SyntheticVerifiedAuthorizationIngressContext,
    SyntheticVerifiedReleaseRecipientContext,
    authorization_ingress_artifact_digest,
    bridge_commitment_suite,
    bridge_commitment_suite_digest,
    bridge_commitment_suite_digest_domain,
    bridge_commitment_suite_mutation_report,
    canonical_history_delivery_domain,
    canonical_history_request_digest,
    canonical_read_request_digest,
    canonical_read_route,
    canonical_scope_digest,
    committed_outbox_artifact_digest,
    dispatch_artifact_digest,
    dispatch_destination_cut_digest,
    dispatch_stable_destination_digest,
    dispatch_transport_gate_state_digest,
    grant_currentness_artifact_digest,
    issue_validated_release_cas_receipt,
    next_grant_release_counter_state_digest,
    observer_read_capture_bridge_profile,
    observer_read_capture_bridge_profile_digest,
    observer_read_capture_bridge_profile_digest_domain,
    observer_read_capture_bridge_profile_mutation_report,
    outbox_commit_receipt_artifact_digest,
    qualified_deadline_mapping_artifact_digest,
    read_decision_artifact_digest,
    release_recipient_artifact_digest,
    seal_authorization_ingress_context,
    seal_boundary_membership,
    seal_committed_outbox_artifact,
    seal_dispatch_context,
    seal_grant_currentness_evidence,
    seal_outbox_commit_receipt,
    seal_qualified_deadline_mapping,
    seal_read_decision,
    seal_release_cas,
    seal_release_recipient_context,
    seal_scope,
    validate_boundary_membership,
    validate_bridge_canonical_type_system,
    validate_committed_outbox_artifact,
    validate_dispatch_context,
    validate_observer_read_capture_bridge_profile,
    validate_read_decision,
    validate_release_cas,
    validate_release_recipient_context,
    validate_scope,
    validated_release_cas_receipt_artifact_digest,
)

if "bounded_json" in sys.modules:
    from bounded_json import (  # type: ignore[import-not-found]  # noqa: E402
        BoundedJsonError,
        JsonLimits,
        parse_json_bytes,
    )
else:
    _REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))
    from scripts.bounded_json import (  # noqa: E402
        BoundedJsonError,
        JsonLimits,
        parse_json_bytes,
    )


class ProbeError(RuntimeError):
    """A synthetic proof obligation failed closed."""


MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_BOUNDARIES = 8
MAX_GRANTS = 16
MAX_ITEMS = 32
MAX_ATTEMPTS = 64
MAX_CANONICAL_COLLECTION_ITEMS = 512
MAX_CANONICAL_STRING_CHARS = 16_384
MAX_AUTHORITY_TRANSITIONS = 128
MAX_AUTHORITY_OBJECTS = 2_048
MAX_AUTHORITY_CONTENT_BYTES = 8 * 1024 * 1024
MAX_AUTHORITY_SIGNED_BYTES = 2 * 1024 * 1024
MAX_AUTHORITY_SIGNED_ENVELOPE_OVERHEAD = 2 * 1024
MAX_AUTHORITY_SIGNED_PAYLOAD_BYTES = (
    MAX_AUTHORITY_SIGNED_BYTES - MAX_AUTHORITY_SIGNED_ENVELOPE_OVERHEAD
)
MAX_AUTHORITY_CANONICAL_BYTES = 32 * 1024 * 1024
MAX_AUTHORITY_INCARNATIONS = 64
MAX_AUTHORITY_CANONICAL_DEPTH = 64
MAX_AUTHORITY_CANONICAL_NODES = 16_384
MAX_AUTHORITY_RECOVERY_NODES = 262_144
MAX_SYNTHETIC_WRITER_LEASE_DURATION = 10_000
SCHEMA_VERSION = 1

SERVER_PRINCIPAL = "body-service"
SERVER_KEY_ID = "body-service:key:7"
SESSION_CREATION_PRINCIPAL = "session-creation-authority"
SESSION_CREATION_KEY_ID = "session-creation-authority:key:3"
SESSION_ID = "synthetic-session"
SESSION_GENERATION = "00000000-0000-4000-8000-000000000001"
REGISTRY_INCARNATION = "00000000-0000-4000-8000-000000000002"
SERVER_STATE_INCARNATION = "00000000-0000-4000-8000-000000000003"
SERVER_CLOCK_1 = "00000000-0000-4000-8000-000000000101"
SERVER_CLOCK_2 = "00000000-0000-4000-8000-000000000102"
OBSERVER_CLOCK_1 = "00000000-0000-4000-8000-000000000201"
OBSERVER_CLOCK_2 = "00000000-0000-4000-8000-000000000202"
SECURITY_STATE_DIGEST = hashlib.sha256(b"authorization-security-1").hexdigest()
SECURITY_STATE_DIGEST_2 = hashlib.sha256(b"authorization-security-2").hexdigest()
AUTHORITY_REALM_KEY = ("body-service", "synthetic-realm")
OBSERVER_PRINCIPAL = "observer-a"
OBSERVER_INSTANCE = "observer-a-instance-1"
CAPABILITY_ISSUER_PRINCIPAL = "observer-capability-issuer"
CAPABILITY_ISSUER_KEY_ID = "observer-capability-issuer:key:5"
CAPABILITY_ISSUER_INCARNATION = "00000000-0000-4000-8000-000000000301"
_CAPABILITY_ISSUER_SEAL_KEY = hashlib.sha256(
    b"NCP-B01-SYNTHETIC-OBSERVER-CAPABILITY-ISSUER-KEY-V1"
).digest()
_READ_DECISION_SEAL_KEY = hashlib.sha256(
    b"NCP-B01-SYNTHETIC-OBSERVER-READ-DECISION-KEY-V1"
).digest()
_TRANSPORT_EVIDENCE_SEAL_KEY = hashlib.sha256(
    b"NCP-B01-SYNTHETIC-TRANSPORT-EVIDENCE-KEY-V1"
).digest()
_PARENT_ALLOCATION_SEAL_KEY = hashlib.sha256(
    b"NCP-B01-SYNTHETIC-PARENT-ALLOCATION-KEY-V1"
).digest()
_SERVER_EXPIRY_POLICY_RULE_DIGEST = hashlib.sha256(
    b"NCP-B01-SYNTHETIC-SERVER-EXPIRY-POLICY-V1"
).hexdigest()
_SERVER_EXPIRY_POLICY_INPUTS_DIGEST = hashlib.sha256(
    b"NCP-B01-SYNTHETIC-SERVER-EXPIRY-INPUTS-V1"
).hexdigest()
_SERVER_EXPIRY_AUTHORITY_SOURCE_RECEIPT_DIGEST = hashlib.sha256(
    b"NCP-B01-SYNTHETIC-TRUSTED-CLOCK-EXPIRY-RECEIPT-V1"
).hexdigest()
TRANSPORT_EVIDENCE_PRINCIPAL = "synthetic-transport-authority"
TRANSPORT_EVIDENCE_KEY_ID = "synthetic-transport-authority:key:1"
TRANSPORT_EVIDENCE_INCARNATION = "00000000-0000-4000-8000-000000000401"
_SYNTHETIC_RECEIPT_SIGNING_KEYS = MappingProxyType(
    {
        key_id: hashlib.sha256(
            b"NCP-B01-SYNTHETIC-RECEIPT-HMAC-KEY-V1\x00" + key_id.encode("ascii")
        ).digest()
        for key_id in (
            SERVER_KEY_ID,
            "delivery-gateway-a:key:4",
            "history-provider-b:key:9",
        )
    }
)
OBSERVER_READ_OPERATIONS = (
    "attach",
    "detach",
    "history_query",
    "renew",
    "subscribe",
)
OBSERVER_WRITE_OR_AUTHORITY_OPERATIONS = frozenset(
    {
        "apply",
        "command",
        "declare_queryable",
        "declare_stream",
        "estop",
        "mutate",
        "publish",
        "put",
        "reset",
    }
)


T = TypeVar("T")
_BUILTIN_ARTIFACT_TYPE_IDS: dict[type[Any], str] = {
    str: "ncp.b01.scalar.string@1",
    int: "ncp.b01.scalar.integer@1",
    bool: "ncp.b01.scalar.boolean@1",
    bytes: "ncp.b01.scalar.bytes@1",
    tuple: "ncp.b01.collection.tuple@1",
    type(None): "ncp.b01.scalar.none@1",
}
_CANONICAL_ARTIFACT_TYPE_IDS: dict[type[Any], str] = {}


def _register_artifact_type(value_type: type[Any], stable_type_id: str) -> None:
    _require(value_type not in _CANONICAL_ARTIFACT_TYPE_IDS, "type registered twice")
    _require(stable_type_id not in _CANONICAL_ARTIFACT_TYPE_IDS.values(), "ID reused")
    _CANONICAL_ARTIFACT_TYPE_IDS[value_type] = stable_type_id


def _stable_artifact_type_id(type_name: str) -> str:
    return f"ncp.b01.artifact.{type_name}@{SCHEMA_VERSION}"


def _artifact_type_id(value_or_type: Any) -> str:
    value_type = value_or_type if type(value_or_type) is type else type(value_or_type)
    builtin = _BUILTIN_ARTIFACT_TYPE_IDS.get(value_type)
    if builtin is not None:
        return builtin
    type_id = _CANONICAL_ARTIFACT_TYPE_IDS.get(value_type)
    _require(type_id is not None, "unregistered canonical artifact type")
    return type_id


def _artifact_field_snapshot(
    value: Any,
) -> tuple[str, tuple[tuple[str, Any], ...]]:
    """Revalidate one registered artifact and read each field exactly once."""

    registry = _CANONICAL_ARTIFACT_TYPE_IDS
    _require(
        type(registry) is FrozenTypeRegistry,
        "canonical artifact registry is not frozen",
    )
    try:
        return registry.snapshot_artifact_view(value)
    except ValueError as exc:
        raise ProbeError("canonical artifact snapshot was rejected") from exc


def _semantic_digest(domain: str, value: Any) -> str:
    _require(
        domain.startswith("ncp.b01.") and domain.endswith("@1"),
        "semantic digest domain is not a stable registered ID",
    )
    return hashlib.sha256(
        b"NCP-B01-SEMANTIC-DIGEST-V1\x00"
        + domain.encode("utf-8")
        + b"\x00"
        + _canonical_bytes(value)
    ).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeError(message)


def _bounded_utf8_octets(value: Any, *, maximum: int, label: str) -> int:
    _require(
        type(value) is str and len(value) <= maximum,
        f"{label} is not an exact bounded string",
    )
    total = 0
    for character in value:
        code_point = ord(character)
        _require(
            not 0xD800 <= code_point <= 0xDFFF,
            f"{label} is not a Unicode scalar sequence",
        )
        total += (
            1
            if code_point <= 0x7F
            else 2
            if code_point <= 0x7FF
            else 3
            if code_point <= 0xFFFF
            else 4
        )
        _require(total <= maximum, f"{label} exceeds its UTF-8 bound")
    return total


_AUTHORITY_CANONICAL_LIMITS = CanonicalLimits(
    max_output_bytes=MAX_AUTHORITY_CANONICAL_BYTES,
    max_depth=MAX_AUTHORITY_CANONICAL_DEPTH,
    max_nodes=MAX_AUTHORITY_CANONICAL_NODES,
    max_collection_items=MAX_CANONICAL_COLLECTION_ITEMS,
    max_artifact_fields=256,
    max_string_bytes=MAX_CANONICAL_STRING_CHARS,
    max_payload_bytes=MAX_AUTHORITY_CONTENT_BYTES,
    max_aggregate_scalar_bytes=MAX_AUTHORITY_CANONICAL_BYTES,
    min_integer=0,
    max_integer=MAX_SAFE_INTEGER,
    allow_empty_payload=True,
)
_AUTHORITY_STORED_VALUE_LIMITS = replace(
    _AUTHORITY_CANONICAL_LIMITS,
    max_output_bytes=MAX_AUTHORITY_CONTENT_BYTES,
    max_aggregate_scalar_bytes=MAX_AUTHORITY_CONTENT_BYTES,
)
_AUTHORITY_SIGNED_SEMANTIC_LIMITS = replace(
    _AUTHORITY_CANONICAL_LIMITS,
    max_output_bytes=MAX_AUTHORITY_SIGNED_PAYLOAD_BYTES,
    max_payload_bytes=MAX_AUTHORITY_SIGNED_PAYLOAD_BYTES,
    max_aggregate_scalar_bytes=MAX_AUTHORITY_SIGNED_PAYLOAD_BYTES,
)
_AUTHORITY_TAGGED_JSON_MAX_DEPTH = 1 + (3 * MAX_AUTHORITY_CANONICAL_DEPTH)
_AUTHORITY_TAGGED_JSON_MAX_ITEMS = 8 + (6 * MAX_AUTHORITY_CANONICAL_NODES)
_AUTHORITY_SIGNED_JSON_LIMITS = CanonicalLimits(
    max_output_bytes=MAX_AUTHORITY_SIGNED_BYTES,
    max_depth=_AUTHORITY_TAGGED_JSON_MAX_DEPTH,
    max_nodes=_AUTHORITY_TAGGED_JSON_MAX_ITEMS,
    max_collection_items=MAX_CANONICAL_COLLECTION_ITEMS,
    max_artifact_fields=0,
    max_string_bytes=MAX_AUTHORITY_SIGNED_BYTES,
    max_payload_bytes=MAX_AUTHORITY_SIGNED_BYTES,
    max_aggregate_scalar_bytes=MAX_AUTHORITY_SIGNED_BYTES,
    min_integer=0,
    max_integer=MAX_SAFE_INTEGER,
    allow_empty_payload=True,
)
_AUTHORITY_SIGNED_PARSE_LIMITS = JsonLimits(
    maximum_bytes=MAX_AUTHORITY_SIGNED_BYTES,
    maximum_depth=_AUTHORITY_TAGGED_JSON_MAX_DEPTH,
    maximum_items=_AUTHORITY_TAGGED_JSON_MAX_ITEMS,
    maximum_object_members=MAX_CANONICAL_COLLECTION_ITEMS,
    maximum_array_items=MAX_CANONICAL_COLLECTION_ITEMS,
    maximum_key_utf8_bytes=MAX_CANONICAL_STRING_CHARS,
    maximum_string_utf8_bytes=MAX_AUTHORITY_SIGNED_BYTES,
    maximum_total_string_utf8_bytes=MAX_AUTHORITY_SIGNED_BYTES,
    maximum_integer_chars=64,
    maximum_float_chars=64,
    allow_floats=False,
)


def _normalize(value: Any) -> Any:
    """Return the bounded tagged JSON view for diagnostics only."""

    return parse_json_bytes(
        _canonical_bytes(value),
        limits=replace(
            _AUTHORITY_SIGNED_PARSE_LIMITS,
            maximum_bytes=MAX_AUTHORITY_CANONICAL_BYTES,
            maximum_key_utf8_bytes=MAX_CANONICAL_STRING_CHARS,
            maximum_string_utf8_bytes=MAX_AUTHORITY_CANONICAL_BYTES,
            maximum_total_string_utf8_bytes=MAX_AUTHORITY_CANONICAL_BYTES,
        ),
        label="canonical authority value",
    )


def _canonical_bytes(value: Any) -> bytes:
    return _bounded_canonical_bytes(
        value,
        style="authority",
        limits=_AUTHORITY_CANONICAL_LIMITS,
        type_ids=_CANONICAL_ARTIFACT_TYPE_IDS,
        error_type=ProbeError,
    )


def _canonical_stored_bytes(value: Any) -> bytes:
    """Encode one storable value under the whole-store content byte ceiling."""

    return _bounded_canonical_bytes(
        value,
        style="authority",
        limits=_AUTHORITY_STORED_VALUE_LIMITS,
        type_ids=_CANONICAL_ARTIFACT_TYPE_IDS,
        error_type=ProbeError,
    )


def _canonical_signed_payload_bytes(value: Any) -> bytes:
    """Encode one receipt payload with a proven envelope-overhead reserve."""

    return _bounded_canonical_bytes(
        value,
        style="authority",
        limits=_AUTHORITY_SIGNED_SEMANTIC_LIMITS,
        type_ids=_CANONICAL_ARTIFACT_TYPE_IDS,
        error_type=ProbeError,
    )


def _canonical_json_bytes(value: Any) -> bytes:
    immutable = (
        freeze_owned(
            value,
            limits=_AUTHORITY_SIGNED_JSON_LIMITS,
            error_type=ProbeError,
            allow_dataclasses=False,
        )
        if type(value) in (dict, list)
        else value
    )
    return _bounded_canonical_bytes(
        immutable,
        style="canonical_json",
        limits=_AUTHORITY_SIGNED_JSON_LIMITS,
        type_ids={},
        error_type=ProbeError,
    )


def _receipt_hmac_key(signing_key_id: Any) -> bytes:
    _require(type(signing_key_id) is str, "receipt signing-key ID is not exact")
    key = _SYNTHETIC_RECEIPT_SIGNING_KEYS.get(signing_key_id)
    _require(
        type(key) is bytes and len(key) == hashlib.sha256().digest_size,
        "receipt signing key is not installed in the external fixture registry",
    )
    return key


def _digest(value: Any) -> str:
    artifact_type_id = _artifact_type_id(value)
    return _typed_digest_from_canonical(
        artifact_type_id,
        _canonical_bytes(value),
    )


def _typed_digest_from_canonical(
    artifact_type_id: str,
    canonical_payload: bytes,
) -> str:
    _require(type(artifact_type_id) is str, "artifact type ID is not exact")
    _require(type(canonical_payload) is bytes, "canonical payload bytes are not exact")
    domain = artifact_type_id.encode("utf-8")
    return hashlib.sha256(
        b"NCP-B01-TYPED-DIGEST-V1\x00" + domain + b"\x00" + canonical_payload
    ).hexdigest()


def _assert_deeply_immutable(value: Any) -> None:
    validate_immutable(
        value,
        limits=_AUTHORITY_CANONICAL_LIMITS,
        type_ids=_CANONICAL_ARTIFACT_TYPE_IDS,
        error_type=ProbeError,
    )


def _uuid_for(value: Any) -> str:
    raw = bytearray(hashlib.sha256(_canonical_bytes(value)).digest()[:16])
    raw[6] = (raw[6] & 0x0F) | 0x40
    raw[8] = (raw[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(raw)))


def _is_uuid4(value: Any) -> bool:
    if type(value) is not str:
        return False
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, ValueError):
        return False
    return parsed.version == 4 and str(parsed) == value


def _safe_int(value: Any) -> bool:
    return type(value) is int and 0 <= value <= MAX_SAFE_INTEGER


def _is_hex64(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_authority_digest(value: Any) -> bool:
    """Accept only a concrete digest where a value can confer authority."""

    return _is_hex64(value) and value != "0" * 64


def _checked_add(left: int, right: int) -> int:
    _require(_safe_int(left) and _safe_int(right), "unsafe checked-add operand")
    result = left + right
    _require(_safe_int(result), "checked-add overflow")
    return result


def _checked_mul(left: int, right: int) -> int:
    _require(_safe_int(left) and _safe_int(right), "unsafe checked-mul operand")
    result = left * right
    _require(_safe_int(result), "checked-mul overflow")
    return result


def _checked_floor_ratio(value: int, numerator: int, denominator: int) -> int:
    _require(denominator > 0, "mapping denominator must be positive")
    return _checked_mul(value, numerator) // denominator


def _checked_ceil_ratio(value: int, numerator: int, denominator: int) -> int:
    _require(denominator > 0, "mapping denominator must be positive")
    product = _checked_mul(value, numerator)
    return _checked_add(product, denominator - 1) // denominator


def _canonical_unique(
    values: Sequence[T],
    *,
    key: Callable[[T], Any] = lambda item: item,
    maximum: int,
    label: str,
) -> tuple[T, ...]:
    _require(0 < len(values) <= maximum, f"{label} size is outside its bound")
    keyed = [(key(value), value) for value in values]
    ordered = sorted(keyed, key=lambda pair: _canonical_bytes(pair[0]))
    _require(keyed == ordered, f"{label} is not in canonical order")
    keys = [item[0] for item in keyed]
    _require(len({_digest(item) for item in keys}) == len(keys), f"duplicate {label}")
    return tuple(values)


def _tuple_map(items: Sequence[tuple[str, T]]) -> dict[str, T]:
    result: dict[str, T] = {}
    for key, value in items:
        _require(type(key) is str, "immutable-map key is not an exact string")
        _require(key not in result, f"duplicate immutable-map key: {key}")
        result[key] = value
    return result


def _append_unique_attempt_identity(
    prior_identities: tuple[str, ...],
    attempt_identity: str,
) -> tuple[str, ...]:
    """Append one attempt without duplicating any prior cross-item identity."""

    _require(
        len(set(prior_identities)) == len(prior_identities)
        and attempt_identity not in prior_identities,
        "external drain attempt identity is reused or prior state is corrupt",
    )
    installed = (*prior_identities, attempt_identity)
    _require(
        installed[:-1] == prior_identities and len(set(installed)) == len(installed),
        "external drain attempt installation duplicated a prior identity",
    )
    return installed


@dataclass(frozen=True)
class SignedArtifact:
    artifact_type: str
    payload_digest: str
    signer_principal: str
    signing_key_id: str
    security_state_digest: str
    signature: str


def _frozen_json_object(pairs: Sequence[tuple[str, Any]]) -> FrozenMap:
    """Build one exact immutable JSON object from unique string-key pairs."""

    _require(
        all(type(key) is str for key, _value in pairs),
        "immutable JSON object key type is not exact",
    )
    ordered = tuple(sorted(pairs, key=lambda pair: pair[0]))
    _require(
        len({key for key, _value in ordered}) == len(ordered),
        "immutable JSON object has a duplicate key",
    )
    return FrozenMap(ordered)


def _signed_artifact(
    payload: Any,
    *,
    signer_principal: str,
    signing_key_id: str,
    security_state_digest: str,
) -> tuple[SignedArtifact, bytes]:
    _require(
        type(signer_principal) is str
        and 1 <= len(signer_principal) <= 128
        and signer_principal.isascii()
        and all(0x21 <= ord(character) <= 0x7E for character in signer_principal)
        and type(signing_key_id) is str
        and 1 <= len(signing_key_id) <= 128
        and signing_key_id.isascii()
        and all(0x21 <= ord(character) <= 0x7E for character in signing_key_id)
        and _is_authority_digest(security_state_digest),
        "signed artifact identity or security fields are not exact bounded ASCII",
    )
    payload_bytes = _canonical_signed_payload_bytes(payload)
    artifact_type = _artifact_type_id(payload)
    _require(
        type(artifact_type) is str
        and 1 <= len(artifact_type) <= 256
        and artifact_type.isascii()
        and all(0x21 <= ord(character) <= 0x7E for character in artifact_type),
        "signed artifact type ID is not exact bounded ASCII",
    )
    payload_digest = _typed_digest_from_canonical(artifact_type, payload_bytes)
    try:
        parsed_payload = parse_json_bytes(
            payload_bytes,
            limits=_AUTHORITY_SIGNED_PARSE_LIMITS,
            label="signed artifact payload",
        )
    except (BoundedJsonError, TypeError, ValueError) as exc:
        raise ProbeError(
            "signed artifact payload is not bounded canonical JSON"
        ) from exc
    frozen_payload = freeze_owned(
        parsed_payload,
        limits=_AUTHORITY_SIGNED_JSON_LIMITS,
        error_type=ProbeError,
        allow_dataclasses=False,
    )
    _require(
        _canonical_json_bytes(frozen_payload) == payload_bytes,
        "signed artifact payload did not survive tagged-JSON freezing",
    )
    protected = _frozen_json_object(
        (
            ("artifact_type", artifact_type),
            ("payload", frozen_payload),
            ("payload_digest", payload_digest),
            ("security_state_digest", security_state_digest),
            ("signer_principal", signer_principal),
            ("signing_key_id", signing_key_id),
        )
    )
    signature = hmac.new(
        _receipt_hmac_key(signing_key_id),
        b"NCP-B01-SYNTHETIC-RECEIPT-HMAC-V1\x00" + _canonical_json_bytes(protected),
        hashlib.sha256,
    ).hexdigest()
    envelope = _frozen_json_object((*protected.entries, ("signature", signature)))
    artifact = SignedArtifact(
        artifact_type=artifact_type,
        payload_digest=payload_digest,
        signer_principal=signer_principal,
        signing_key_id=signing_key_id,
        security_state_digest=security_state_digest,
        signature=signature,
    )
    envelope_bytes = _canonical_json_bytes(envelope)
    _require(
        len(envelope_bytes) <= MAX_AUTHORITY_SIGNED_BYTES
        and len(envelope_bytes) - len(payload_bytes)
        <= MAX_AUTHORITY_SIGNED_ENVELOPE_OVERHEAD,
        "signed artifact envelope exceeded its proven overhead reserve",
    )
    return artifact, envelope_bytes


_SIGNED_ENVELOPE_KEYS = frozenset(
    {
        "artifact_type",
        "payload",
        "payload_digest",
        "security_state_digest",
        "signature",
        "signer_principal",
        "signing_key_id",
    }
)


def _parse_signed_envelope(blob: bytes) -> dict[str, Any]:
    try:
        envelope = parse_json_bytes(
            blob,
            limits=_AUTHORITY_SIGNED_PARSE_LIMITS,
            label="signed artifact envelope",
        )
    except (BoundedJsonError, TypeError, ValueError) as exc:
        raise ProbeError("signed artifact bytes are not canonical JSON") from exc
    _require(
        type(envelope) is dict
        and len(envelope) == len(_SIGNED_ENVELOPE_KEYS)
        and frozenset(envelope) == _SIGNED_ENVELOPE_KEYS,
        "signed artifact envelope is not the exact closed object",
    )
    return envelope


def _verify_signed_bytes(
    payload: Any,
    blob: bytes,
    *,
    expected_principal: str,
    expected_key_id: str,
    expected_security_state: str,
) -> None:
    envelope = _parse_signed_envelope(blob)
    _require(
        _canonical_json_bytes(envelope) == blob,
        "signed artifact bytes are not canonical",
    )
    _require(
        envelope["artifact_type"] == _artifact_type_id(payload),
        "type mismatch",
    )
    _require(
        _canonical_json_bytes(envelope["payload"])
        == _canonical_signed_payload_bytes(payload),
        "payload byte mismatch",
    )
    _require(envelope["payload_digest"] == _digest(payload), "payload digest mismatch")
    _require(
        envelope["signer_principal"] == expected_principal,
        "receipt signer principal mismatch",
    )
    _require(
        envelope["signing_key_id"] == expected_key_id,
        "receipt signing key is not the installed current key",
    )
    _require(
        envelope["security_state_digest"] == expected_security_state,
        "receipt security state mismatch",
    )
    protected = {key: value for key, value in envelope.items() if key != "signature"}
    expected_signature = hmac.new(
        _receipt_hmac_key(expected_key_id),
        b"NCP-B01-SYNTHETIC-RECEIPT-HMAC-V1\x00" + _canonical_json_bytes(protected),
        hashlib.sha256,
    ).hexdigest()
    _require(
        type(envelope["signature"]) is str
        and hmac.compare_digest(envelope["signature"], expected_signature),
        "signature mismatch",
    )


@dataclass(frozen=True)
class ParentSelectorAllocationReceipt:
    parent_principal: str
    parent_signing_key_id: str
    parent_security_state_digest: str
    allocated_store_id: str
    allocated_state_incarnation: str
    allocated_selector_version: int
    never_previously_used: bool
    signature: str


def _parent_allocation_receipt(
    *,
    store_id: str,
    state_incarnation: str,
) -> ParentSelectorAllocationReceipt:
    unsigned = (
        SESSION_CREATION_PRINCIPAL,
        SESSION_CREATION_KEY_ID,
        SECURITY_STATE_DIGEST,
        store_id,
        state_incarnation,
        0,
        True,
    )
    signature = hmac.new(
        _PARENT_ALLOCATION_SEAL_KEY,
        b"NCP-B01-SYNTHETIC-PARENT-ALLOCATION-HMAC-V1\x00"
        + _semantic_digest(
            "ncp.b01.ParentSelectorAllocationReceipt.unsigned@1",
            unsigned,
        ).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return ParentSelectorAllocationReceipt(
        parent_principal=SESSION_CREATION_PRINCIPAL,
        parent_signing_key_id=SESSION_CREATION_KEY_ID,
        parent_security_state_digest=SECURITY_STATE_DIGEST,
        allocated_store_id=store_id,
        allocated_state_incarnation=state_incarnation,
        allocated_selector_version=0,
        never_previously_used=True,
        signature=signature,
    )


def _validate_parent_allocation(
    receipt: ParentSelectorAllocationReceipt,
    *,
    store_id: str,
    state_incarnation: str,
) -> None:
    _require(
        type(receipt) is ParentSelectorAllocationReceipt,
        "parent selector allocation receipt type is not exact",
    )
    expected = _parent_allocation_receipt(
        store_id=store_id,
        state_incarnation=state_incarnation,
    )
    _require(
        receipt == expected
        and hmac.compare_digest(receipt.signature, expected.signature),
        "parent selector allocation fixture authentication failed",
    )


@dataclass(frozen=True)
class CommitTimeDeadlineCondition:
    intent_digest: str
    evaluation_set_digest: str
    evaluation_index: int
    evaluation_count: int
    store_id: str
    authority_principal: str
    transition_kind: str
    operation_id: str
    expected_prior_state_digest: str | None
    expected_prior_selector_version: int
    installed_successor_digest: str
    installed_selector_version: int
    security_state_digest: str
    purpose: str
    deadline_kind: str
    commit_clock_incarnation: str
    trusted_commit_time_sample: int
    exclusive_deadline: int
    deadline_predicate_result: bool
    qualified_effective_deadline_margin: int
    authorization_linearization_mode: str
    qualified_completion_bound: int
    timing_qualification_digest: str | None
    enforced_completion_or_abort_evidence_digest: str | None
    transaction_manager_guarantee: str


AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE = "AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE"
EXPIRY_AT_OR_AFTER_EXCLUSIVE_DEADLINE = "EXPIRY_AT_OR_AFTER_EXCLUSIVE_DEADLINE"
DEADLINE_KINDS = frozenset(
    {
        "SERVER_GRANT_INSTALLATION_CLOSE",
        "SERVER_GRANT_NOT_AFTER",
        "BOUNDARY_GRANT_PREPARATION_CLOSE",
        "BOUNDARY_GRANT_RELEASE_NOT_AFTER",
        "OBSERVER_GRANT_RESPONSE_CLOSE",
        "OBSERVER_GRANT_ADMISSION_NOT_AFTER",
    }
)


def _deadline_condition(
    *,
    intent: AuthorizationDeadlineConditionIntent,
    commit_time: int,
    evaluation_set_digest: str,
    evaluation_index: int,
    evaluation_count: int,
    installed_successor_digest: str,
    installed_selector_version: int,
) -> CommitTimeDeadlineCondition:
    _require(
        intent.purpose
        in {
            AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE,
            EXPIRY_AT_OR_AFTER_EXCLUSIVE_DEADLINE,
        },
        "unknown deadline purpose",
    )
    _require(intent.deadline_kind in DEADLINE_KINDS, "unknown deadline kind")
    _require(_safe_int(commit_time), "unsafe commit-time sample")
    effective_sample = _checked_add(
        commit_time,
        intent.qualified_effective_deadline_margin,
    )
    if intent.purpose == AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE:
        result = effective_sample < intent.exclusive_deadline
    else:
        result = commit_time >= intent.exclusive_deadline
    condition = CommitTimeDeadlineCondition(
        intent_digest=_digest(intent),
        evaluation_set_digest=evaluation_set_digest,
        evaluation_index=evaluation_index,
        evaluation_count=evaluation_count,
        store_id=intent.store_id,
        authority_principal=intent.authority_principal,
        transition_kind=intent.transition_kind,
        operation_id=intent.operation_id,
        expected_prior_state_digest=intent.expected_prior_state_digest,
        expected_prior_selector_version=(intent.expected_prior_selector_version),
        installed_successor_digest=installed_successor_digest,
        installed_selector_version=installed_selector_version,
        security_state_digest=intent.security_state_digest,
        purpose=intent.purpose,
        deadline_kind=intent.deadline_kind,
        commit_clock_incarnation=intent.clock_incarnation,
        trusted_commit_time_sample=commit_time,
        exclusive_deadline=intent.exclusive_deadline,
        deadline_predicate_result=result,
        qualified_effective_deadline_margin=(intent.qualified_completion_bound),
        authorization_linearization_mode=intent.authorization_linearization_mode,
        qualified_completion_bound=intent.qualified_completion_bound,
        timing_qualification_digest=intent.timing_qualification_digest,
        enforced_completion_or_abort_evidence_digest=(
            None
            if intent.authorization_linearization_mode
            == "TRANSACTION_MANAGER_LINEARIZATION"
            else _digest(
                (
                    "ENFORCED_COMPLETION_OR_ABORT",
                    _digest(intent),
                    commit_time,
                    result,
                )
            )
        ),
        transaction_manager_guarantee="CLOCK_PREDICATE_AND_POINTER_APPLY_ONE_LOCK",
    )
    _require(result, f"deadline condition failed: {intent.deadline_kind}")
    return condition


def _validate_condition(
    condition: CommitTimeDeadlineCondition,
    *,
    intent: AuthorizationDeadlineConditionIntent,
    evaluation_set_digest: str,
    evaluation_index: int,
    evaluation_count: int,
    installed_successor_digest: str,
    installed_selector_version: int,
) -> None:
    _require(condition.intent_digest == _digest(intent), "deadline intent mismatch")
    _require(
        condition.evaluation_set_digest == evaluation_set_digest,
        "deadline evaluation-set mismatch",
    )
    _require(condition.evaluation_index == evaluation_index, "evaluation index drift")
    _require(condition.evaluation_count == evaluation_count, "evaluation count drift")
    _require(condition.store_id == intent.store_id, "deadline store substitution")
    _require(
        condition.authority_principal == intent.authority_principal,
        "deadline authority substitution",
    )
    _require(
        condition.transition_kind == intent.transition_kind,
        "deadline transition substitution",
    )
    _require(condition.operation_id == intent.operation_id, "operation substitution")
    _require(
        condition.expected_prior_state_digest == intent.expected_prior_state_digest,
        "deadline prior-state substitution",
    )
    _require(
        condition.expected_prior_selector_version
        == intent.expected_prior_selector_version,
        "deadline selector-version substitution",
    )
    _require(
        condition.installed_successor_digest == installed_successor_digest,
        "deadline installed-successor substitution",
    )
    _require(
        condition.installed_selector_version == installed_selector_version,
        "deadline installed-selector substitution",
    )
    _require(
        condition.security_state_digest == intent.security_state_digest,
        "deadline security-state substitution",
    )
    _require(condition.purpose == intent.purpose, "deadline purpose substitution")
    _require(
        condition.deadline_kind == intent.deadline_kind,
        "deadline kind substitution",
    )
    _require(
        condition.commit_clock_incarnation == intent.clock_incarnation,
        "deadline clock mismatch",
    )
    _require(
        condition.exclusive_deadline == intent.exclusive_deadline,
        "deadline value mismatch",
    )
    _require(
        condition.transaction_manager_guarantee
        == "CLOCK_PREDICATE_AND_POINTER_APPLY_ONE_LOCK",
        "commit-time predicate is not integrated with atomic apply",
    )
    _require(
        condition.authorization_linearization_mode
        == intent.authorization_linearization_mode,
        "authorization-linearization mode mismatch",
    )
    _require(
        condition.qualified_completion_bound
        == intent.qualified_completion_bound
        == condition.qualified_effective_deadline_margin,
        "completion bound mismatch",
    )
    if condition.authorization_linearization_mode == (
        "TRANSACTION_MANAGER_LINEARIZATION"
    ):
        _require(
            condition.qualified_completion_bound == 0
            and condition.timing_qualification_digest is None
            and condition.enforced_completion_or_abort_evidence_digest is None,
            "linearization mode must have zero bound and no free qualification",
        )
    elif condition.authorization_linearization_mode == ("QUALIFIED_COMPLETION_BOUND"):
        _require(
            condition.qualified_completion_bound > 0
            and condition.timing_qualification_digest is not None
            and condition.enforced_completion_or_abort_evidence_digest is not None,
            "qualified completion bound lacks qualification and abort evidence",
        )
    else:
        raise ProbeError("unknown authorization-linearization mode")
    expected = (
        _checked_add(
            condition.trusted_commit_time_sample,
            condition.qualified_effective_deadline_margin,
        )
        < intent.exclusive_deadline
        if intent.purpose == AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE
        else condition.trusted_commit_time_sample >= intent.exclusive_deadline
    )
    _require(expected and condition.deadline_predicate_result, "false deadline result")


@dataclass(frozen=True)
class AuthenticatedClockMapping:
    coordinator_clock_incarnation: str
    boundary_clock_incarnation: str
    coordinator_reference: int
    boundary_reference_lower: int
    boundary_reference_upper: int
    source_applicability_start: int
    source_applicability_end: int
    target_applicability_start: int
    target_applicability_end: int
    minimum_rate_numerator: int
    minimum_rate_denominator: int
    maximum_rate_numerator: int
    maximum_rate_denominator: int
    rounding_rule: str
    correlation_authority: str
    qualification_digest: str
    source_receipt_digest: str
    source_receipt_authority: str
    source_receipt_current: bool


def _validate_mapping(mapping: AuthenticatedClockMapping) -> None:
    integer_fields = (
        mapping.coordinator_reference,
        mapping.boundary_reference_lower,
        mapping.boundary_reference_upper,
        mapping.source_applicability_start,
        mapping.source_applicability_end,
        mapping.target_applicability_start,
        mapping.target_applicability_end,
        mapping.minimum_rate_numerator,
        mapping.minimum_rate_denominator,
        mapping.maximum_rate_numerator,
        mapping.maximum_rate_denominator,
    )
    _require(all(_safe_int(item) for item in integer_fields), "unsafe mapping integer")
    _require(
        mapping.minimum_rate_denominator > 0 and mapping.maximum_rate_denominator > 0,
        "mapping denominator must be positive",
    )
    _require(
        mapping.minimum_rate_numerator > 0 and mapping.maximum_rate_numerator > 0,
        "mapping rate must be positive",
    )
    _require(
        mapping.boundary_reference_lower <= mapping.boundary_reference_upper,
        "mapping reference interval inverted",
    )
    _require(
        mapping.source_applicability_start
        <= mapping.coordinator_reference
        <= mapping.source_applicability_end,
        "mapping reference outside horizon",
    )
    _require(
        mapping.target_applicability_start
        <= mapping.boundary_reference_lower
        <= mapping.boundary_reference_upper
        <= mapping.target_applicability_end,
        "mapping target reference outside horizon",
    )
    _require(mapping.rounding_rule == "LOWER_FLOOR_UPPER_CEIL", "unknown rounding")
    _require(bool(mapping.correlation_authority), "mapping lacks authority")
    _require(
        mapping.source_receipt_authority == mapping.correlation_authority
        and mapping.source_receipt_current,
        "mapping source receipt is not current under its authority",
    )
    _require(
        _is_authority_digest(mapping.qualification_digest),
        "bad qualification digest",
    )
    _require(
        _is_authority_digest(mapping.source_receipt_digest),
        "bad mapping source receipt",
    )
    left = _checked_mul(
        mapping.minimum_rate_numerator,
        mapping.maximum_rate_denominator,
    )
    right = _checked_mul(
        mapping.maximum_rate_numerator,
        mapping.minimum_rate_denominator,
    )
    _require(left <= right, "minimum mapping rate exceeds maximum")


def _mapping_delta(mapping: AuthenticatedClockMapping, source_time: int) -> int:
    _validate_mapping(mapping)
    _require(
        mapping.source_applicability_start
        <= source_time
        <= mapping.source_applicability_end,
        "mapped instant outside applicability horizon",
    )
    _require(
        source_time >= mapping.coordinator_reference,
        "fixture mapping does not authorize reverse-time extrapolation",
    )
    return source_time - mapping.coordinator_reference


def _map_lower(mapping: AuthenticatedClockMapping, source_time: int) -> int:
    delta = _mapping_delta(mapping, source_time)
    advance = _checked_floor_ratio(
        delta,
        mapping.minimum_rate_numerator,
        mapping.minimum_rate_denominator,
    )
    result = _checked_add(mapping.boundary_reference_lower, advance)
    _require(
        mapping.target_applicability_start
        <= result
        <= mapping.target_applicability_end,
        "mapped lower image outside target horizon",
    )
    return result


def _map_upper(mapping: AuthenticatedClockMapping, source_time: int) -> int:
    delta = _mapping_delta(mapping, source_time)
    advance = _checked_ceil_ratio(
        delta,
        mapping.maximum_rate_numerator,
        mapping.maximum_rate_denominator,
    )
    result = _checked_add(mapping.boundary_reference_upper, advance)
    _require(
        mapping.target_applicability_start
        <= result
        <= mapping.target_applicability_end,
        "mapped upper image outside target horizon",
    )
    return result


def _map_duration_upper(
    mapping: AuthenticatedClockMapping,
    duration: int,
    *,
    source_anchor: int,
) -> int:
    _validate_mapping(mapping)
    _require(duration > 0, "activation budget must be positive")
    _require(
        mapping.source_applicability_start <= source_anchor,
        "duration anchor precedes source horizon",
    )
    _require(
        _checked_add(source_anchor, duration) <= mapping.source_applicability_end,
        "duration endpoint exceeds source horizon",
    )
    return _checked_ceil_ratio(
        duration,
        mapping.maximum_rate_numerator,
        mapping.maximum_rate_denominator,
    )


@dataclass(frozen=True)
class BoundaryMember:
    boundary_principal: str
    boundary_instance: str
    delivery_domain: str
    deadline_policy_id: str
    read_scope: CanonicalObserverReadScope
    scope_membership: ObserverBoundaryReadScopeMembership
    security_state_digest: str
    security_key_id: str
    clock_mapping: AuthenticatedClockMapping

    @property
    def exact_scope_digest(self) -> str:
        return self.read_scope.scope_digest

    @property
    def scope_membership_digest(self) -> str:
        return self.scope_membership.membership_digest

    @property
    def identity(self) -> tuple[str, ...]:
        return (
            self.boundary_principal,
            self.boundary_instance,
            self.delivery_domain,
            self.deadline_policy_id,
            self.exact_scope_digest,
            self.scope_membership_digest,
            self.security_state_digest,
            self.security_key_id,
        )


@dataclass(frozen=True)
class BoundaryDeadline:
    boundary_principal: str
    boundary_instance: str
    boundary_clock_incarnation: str
    boundary_prepare_close: int
    boundary_release_not_after: int
    boundary_latest_server_activation_at: int
    boundary_minimum_activation_budget_upper: int
    limiting_server_deadline: str


def _clock_le(
    left_clock: str,
    left: int,
    right_clock: str,
    right: int,
) -> bool:
    _require(left_clock == right_clock, "cross-clock numeric comparison rejected")
    _require(_safe_int(left) and _safe_int(right), "unsafe clock comparison")
    return left <= right


def _clock_lt(
    left_clock: str,
    left: int,
    right_clock: str,
    right: int,
) -> bool:
    _require(left_clock == right_clock, "cross-clock numeric comparison rejected")
    _require(_safe_int(left) and _safe_int(right), "unsafe clock comparison")
    return left < right


@dataclass(frozen=True)
class ObserverGrantRegistryKey:
    requester_principal: str
    grant_lineage_incarnation: str


@dataclass(frozen=True)
class TrustedDeliveryBoundaryGrantKey:
    logical_session: str
    session_generation: str
    registry_incarnation: str
    registry_key: ObserverGrantRegistryKey
    issuance_sequence: int
    canonical_grant_digest: str


@dataclass(frozen=True)
class ObserverGrantBoundaryInstallationPlan:
    stable_registry_key: ObserverGrantRegistryKey
    proposed_issuance_sequence: int
    proposed_issuance_context_digest: str
    originating_operation: str
    operation_challenge: str
    operation_context_digest: str
    logical_session: str
    session_generation: str
    descriptor_revision: int
    descriptor_digest: str
    privacy_policy_digest: str
    security_state_digest: str
    security_epoch: int
    revocation_epoch: int
    exact_scope_digests: tuple[str, ...]
    boundary_members: tuple[BoundaryMember, ...]
    boundary_deadlines: tuple[BoundaryDeadline, ...]
    coordinator_clock_policy_id: str
    coordinator_clock_incarnation: str
    server_request_time: int
    server_grant_installation_close: int
    server_grant_not_after: int
    minimum_boundary_activation_budget: int
    maximum_boundary_revocation_lag: int
    server_deadline_policy_id: str
    observer_deadline_policy_id: str


@dataclass(frozen=True)
class ObserverGrant:
    requester_principal: str
    grant_lineage_incarnation: str
    grant_id: str
    grant_incarnation: str
    issuance_nonce: str
    issuance_sequence: int
    issuance_context_digest: str
    logical_session: str
    session_generation: str
    descriptor_revision: int
    descriptor_digest: str
    privacy_policy_digest: str
    security_state_digest: str
    security_epoch: int
    revocation_epoch: int
    exact_scope_digests: tuple[str, ...]
    exact_boundary_member_identities: tuple[tuple[str, ...], ...]
    operation_challenge: str
    operation_context_digest: str
    issuer_utc_not_before: int
    issuer_utc_not_after: int
    maximum_live_duration: int
    server_deadline_policy_id: str
    observer_deadline_policy_id: str
    boundary_installation_plan_digest: str


def _derive_boundary_deadline(
    member: BoundaryMember,
    *,
    request_time: int,
    installation_close: int,
    grant_not_after: int,
    minimum_budget: int,
    maximum_lag: int,
) -> BoundaryDeadline:
    mapping = member.clock_mapping
    _require(
        mapping.coordinator_reference <= request_time,
        "clock calibration occurs after the original request",
    )
    request_plus_lag = _checked_add(request_time, maximum_lag)
    effective_not_after = min(grant_not_after, request_plus_lag)
    _require(
        mapping.source_applicability_start <= request_time,
        "mapping source horizon starts after original request",
    )
    _require(
        _checked_add(installation_close, minimum_budget)
        <= mapping.source_applicability_end,
        "mapping source horizon omits the activation-budget endpoint",
    )
    _require(
        effective_not_after <= mapping.source_applicability_end,
        "mapping source horizon omits effective expiry",
    )
    _require(
        mapping.boundary_clock_incarnation != mapping.coordinator_clock_incarnation,
        "fixture must exercise distinct boundary clocks",
    )
    limiting = (
        "REQUEST_PLUS_MAXIMUM_REVOCATION_LAG"
        if request_plus_lag < grant_not_after
        else "SERVER_GRANT_NOT_AFTER"
    )
    prepare_close = _map_lower(mapping, installation_close)
    latest_activation = _map_upper(mapping, installation_close)
    release_not_after = _map_lower(mapping, effective_not_after)
    budget_upper = _map_duration_upper(
        mapping,
        minimum_budget,
        source_anchor=installation_close,
    )
    _require(
        _clock_le(
            mapping.boundary_clock_incarnation,
            prepare_close,
            mapping.boundary_clock_incarnation,
            latest_activation,
        )
        and _clock_lt(
            mapping.boundary_clock_incarnation,
            latest_activation,
            mapping.boundary_clock_incarnation,
            release_not_after,
        ),
        "boundary absolute deadline order is infeasible",
    )
    _require(
        _clock_le(
            mapping.boundary_clock_incarnation,
            _checked_add(latest_activation, budget_upper),
            mapping.boundary_clock_incarnation,
            release_not_after,
        ),
        "boundary activation budget does not fit",
    )
    return BoundaryDeadline(
        boundary_principal=member.boundary_principal,
        boundary_instance=member.boundary_instance,
        boundary_clock_incarnation=mapping.boundary_clock_incarnation,
        boundary_prepare_close=prepare_close,
        boundary_release_not_after=release_not_after,
        boundary_latest_server_activation_at=latest_activation,
        boundary_minimum_activation_budget_upper=budget_upper,
        limiting_server_deadline=limiting,
    )


def _build_plan(
    *,
    key: ObserverGrantRegistryKey,
    issuance_sequence: int,
    issuance_context_digest: str,
    operation: str,
    challenge: str,
    context_digest: str,
    descriptor_revision: int,
    descriptor_digest: str,
    privacy_policy_digest: str,
    members: Sequence[BoundaryMember],
    scope_digests: Sequence[str],
    server_clock: str,
    request_time: int,
    installation_close: int,
    grant_not_after: int,
    minimum_budget: int,
    maximum_lag: int,
) -> ObserverGrantBoundaryInstallationPlan:
    _require(_safe_int(issuance_sequence) and issuance_sequence > 0, "bad issuance")
    _require(request_time < installation_close, "request must precede close")
    _require(minimum_budget > 0, "minimum activation budget must be positive")
    request_plus_lag = _checked_add(request_time, maximum_lag)
    _require(
        _checked_add(installation_close, minimum_budget)
        <= min(grant_not_after, request_plus_lag),
        "server activation budget does not fit",
    )
    canonical_members = _canonical_unique(
        tuple(members),
        key=lambda item: item.identity,
        maximum=MAX_BOUNDARIES,
        label="boundary member set",
    )
    canonical_scopes = _canonical_unique(
        tuple(scope_digests),
        maximum=32,
        label="scope set",
    )
    deadlines = tuple(
        _derive_boundary_deadline(
            member,
            request_time=request_time,
            installation_close=installation_close,
            grant_not_after=grant_not_after,
            minimum_budget=minimum_budget,
            maximum_lag=maximum_lag,
        )
        for member in canonical_members
    )
    return ObserverGrantBoundaryInstallationPlan(
        stable_registry_key=key,
        proposed_issuance_sequence=issuance_sequence,
        proposed_issuance_context_digest=issuance_context_digest,
        originating_operation=operation,
        operation_challenge=challenge,
        operation_context_digest=context_digest,
        logical_session=SESSION_ID,
        session_generation=SESSION_GENERATION,
        descriptor_revision=descriptor_revision,
        descriptor_digest=descriptor_digest,
        privacy_policy_digest=privacy_policy_digest,
        security_state_digest=SECURITY_STATE_DIGEST,
        security_epoch=7,
        revocation_epoch=11,
        exact_scope_digests=canonical_scopes,
        boundary_members=canonical_members,
        boundary_deadlines=deadlines,
        coordinator_clock_policy_id="SERVER_MONOTONIC_ADVANCES_ACROSS_SUSPEND",
        coordinator_clock_incarnation=server_clock,
        server_request_time=request_time,
        server_grant_installation_close=installation_close,
        server_grant_not_after=grant_not_after,
        minimum_boundary_activation_budget=minimum_budget,
        maximum_boundary_revocation_lag=maximum_lag,
        server_deadline_policy_id="SERVER_POLICY_V1",
        observer_deadline_policy_id="OBSERVER_POLICY_V1",
    )


def _seal_grant(
    plan: ObserverGrantBoundaryInstallationPlan,
    *,
    sequence_label: str,
) -> ObserverGrant:
    _require(
        type(plan) is ObserverGrantBoundaryInstallationPlan,
        "pregrant plan type is not exact",
    )
    _plan_type_id, plan_snapshot = _artifact_field_snapshot(plan)
    plan_values = dict(plan_snapshot)
    plan_fields = set(plan_values)
    _require(
        "canonical_grant_digest" not in plan_fields
        and "full_boundary_key" not in plan_fields,
        "pregrant plan contains a future grant identity",
    )
    stable_registry_key = plan_values["stable_registry_key"]
    boundary_members = plan_values["boundary_members"]
    return ObserverGrant(
        requester_principal=stable_registry_key.requester_principal,
        grant_lineage_incarnation=(stable_registry_key.grant_lineage_incarnation),
        grant_id=_uuid_for(("grant-id", sequence_label)),
        grant_incarnation=_uuid_for(("grant-incarnation", sequence_label)),
        issuance_nonce=_uuid_for(("issuance-nonce", sequence_label)),
        issuance_sequence=plan_values["proposed_issuance_sequence"],
        issuance_context_digest=plan_values["proposed_issuance_context_digest"],
        logical_session=plan_values["logical_session"],
        session_generation=plan_values["session_generation"],
        descriptor_revision=plan_values["descriptor_revision"],
        descriptor_digest=plan_values["descriptor_digest"],
        privacy_policy_digest=plan_values["privacy_policy_digest"],
        security_state_digest=plan_values["security_state_digest"],
        security_epoch=plan_values["security_epoch"],
        revocation_epoch=plan_values["revocation_epoch"],
        exact_scope_digests=plan_values["exact_scope_digests"],
        exact_boundary_member_identities=tuple(
            member.identity for member in boundary_members
        ),
        operation_challenge=plan_values["operation_challenge"],
        operation_context_digest=plan_values["operation_context_digest"],
        issuer_utc_not_before=1_900_000_000,
        issuer_utc_not_after=1_900_000_100,
        maximum_live_duration=100,
        server_deadline_policy_id=plan_values["server_deadline_policy_id"],
        observer_deadline_policy_id=plan_values["observer_deadline_policy_id"],
        boundary_installation_plan_digest=_digest(plan),
    )


def _full_key(
    plan: ObserverGrantBoundaryInstallationPlan,
    grant: ObserverGrant,
) -> TrustedDeliveryBoundaryGrantKey:
    _require(
        type(plan) is ObserverGrantBoundaryInstallationPlan
        and type(grant) is ObserverGrant,
        "plan or grant type is not exact",
    )
    _assert_deeply_immutable(plan)
    _assert_deeply_immutable(grant)
    _require(
        grant.boundary_installation_plan_digest == _digest(plan),
        "grant does not bind its pregrant plan",
    )
    return TrustedDeliveryBoundaryGrantKey(
        logical_session=plan.logical_session,
        session_generation=plan.session_generation,
        registry_incarnation=REGISTRY_INCARNATION,
        registry_key=plan.stable_registry_key,
        issuance_sequence=grant.issuance_sequence,
        canonical_grant_digest=_digest(grant),
    )


@dataclass(frozen=True)
class AtomicTransitionRecord:
    store_id: str
    authority_principal: str
    transition_kind: str
    operation_id: str
    operation_commitment_digest: str
    prior_state_digest: str | None
    installed_state_digest: str
    selector_digest: str
    selector_version: int
    generic_commit_digest: str
    specialized_receipt_digests: tuple[str, ...]
    specialized_receipt_types: tuple[str, ...]
    required_specialized_receipt_types: tuple[str, ...]
    co_committed_object_digests: tuple[str, ...]
    co_committed_object_types: tuple[str, ...]
    required_co_committed_object_types: tuple[str, ...]
    exact_commit_time: int
    commit_clock_incarnation: str
    signing_key_id: str
    security_state_digest: str
    deadline_intent_set_digest: str | None
    deadline_evaluation_set_digest: str | None


@dataclass(frozen=True)
class ImmutableAuthoritySnapshot:
    store_id: str
    authority_principal: str
    authority_key_id: str
    security_state_digest: str
    clock_incarnation: str
    snapshot_version: int
    state: Any | None
    state_digest: str | None
    objects: tuple[tuple[str, Any], ...]
    content_bytes: tuple[tuple[str, bytes], ...]
    signed_bytes: tuple[tuple[str, bytes], ...]
    transitions: tuple[AtomicTransitionRecord, ...]
    used_state_incarnations: tuple[str, ...]
    used_clock_incarnations: tuple[str, ...]
    used_signing_keys: tuple[str, ...]
    retired_signing_keys: tuple[str, ...]
    clock_sample_high_watermarks: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class AtomicReceiptContext:
    store_id: str
    authority_principal: str
    transition_kind: str
    operation_id: str
    operation_commitment_digest: str
    prior_state_digest: str | None
    installed_state_digest: str
    selector_version: int
    commit_clock_incarnation: str
    exact_commit_time: int
    signing_key_id: str
    security_state_digest: str
    deadline_intents: tuple[AuthorizationDeadlineConditionIntent, ...]
    deadline_conditions: tuple[CommitTimeDeadlineCondition, ...]


@dataclass(frozen=True)
class AtomicReceiptBundle:
    generic_commit_payload: Any
    selector: Any
    specialized_payloads: tuple[Any, ...]
    co_committed_objects: tuple[Any, ...] = ()


@dataclass(frozen=True)
class AtomicCandidate:
    expected_snapshot_version: int
    expected_state_digest: str | None
    state: Any
    objects: tuple[Any, ...]
    transition_kind: str
    operation_id: str
    deadline_intents: tuple[AuthorizationDeadlineConditionIntent, ...]
    receipt_builder: Callable[[AtomicReceiptContext], AtomicReceiptBundle]
    next_clock_incarnation: str | None = None
    next_security_state_digest: str | None = None
    next_authority_key_id: str | None = None
    allocate_state_incarnation: str | None = None


@dataclass(frozen=True)
class AuthorityTransitionOperationCommitment:
    store_id: str
    authority_principal: str
    transition_kind: str
    operation_id: str
    expected_prior_state_digest: str | None
    expected_prior_selector_version: int
    candidate_successor_digest: str
    receipt_free_object_digests: tuple[str, ...]
    deadline_intent_set_digest: str | None
    generic_commit_type_id: str
    specialized_receipt_type_ids: tuple[str, ...]
    co_committed_object_type_ids: tuple[str, ...]
    next_clock_incarnation: str | None
    next_security_state_digest: str | None
    next_authority_key_id: str | None
    allocated_state_incarnation: str | None


def _candidate_operation_commitment(
    candidate: AtomicCandidate,
    *,
    store_id: str,
    authority_principal: str,
) -> AuthorityTransitionOperationCommitment:
    generic_name, specialized_names = _receipt_schema(
        store_id,
        candidate.transition_kind,
    )
    receipt_free_object_digests = tuple(
        sorted({_digest(item) for item in candidate.objects})
    )
    return AuthorityTransitionOperationCommitment(
        store_id=store_id,
        authority_principal=authority_principal,
        transition_kind=candidate.transition_kind,
        operation_id=candidate.operation_id,
        expected_prior_state_digest=candidate.expected_state_digest,
        expected_prior_selector_version=candidate.expected_snapshot_version,
        candidate_successor_digest=_digest(candidate.state),
        receipt_free_object_digests=receipt_free_object_digests,
        deadline_intent_set_digest=(
            _intent_set_digest(candidate.deadline_intents)
            if candidate.deadline_intents
            else None
        ),
        generic_commit_type_id=_stable_artifact_type_id(generic_name),
        specialized_receipt_type_ids=tuple(
            _stable_artifact_type_id(item) for item in specialized_names
        ),
        co_committed_object_type_ids=tuple(
            _stable_artifact_type_id(item)
            for item in _co_committed_object_schema(
                store_id,
                candidate.transition_kind,
            )
        ),
        next_clock_incarnation=candidate.next_clock_incarnation,
        next_security_state_digest=candidate.next_security_state_digest,
        next_authority_key_id=candidate.next_authority_key_id,
        allocated_state_incarnation=candidate.allocate_state_incarnation,
    )


def _preflight_stored_value_group(
    values: tuple[Any, ...],
    *,
    label: str,
) -> tuple[bytes, ...]:
    """Bound a whole staged graph before any content digest or map insertion."""

    _require(
        type(values) is tuple and len(values) <= (1 + (2 * MAX_ITEMS)),
        f"{label} collection shape is outside its bound",
    )
    validate_immutable(
        values,
        limits=replace(
            _AUTHORITY_STORED_VALUE_LIMITS,
            max_depth=MAX_AUTHORITY_CANONICAL_DEPTH + 1,
            max_nodes=MAX_AUTHORITY_RECOVERY_NODES + 1,
        ),
        type_ids=_CANONICAL_ARTIFACT_TYPE_IDS,
        error_type=ProbeError,
    )
    encoded = tuple(_canonical_stored_bytes(value) for value in values)
    _require(
        sum(len(value) for value in encoded) <= MAX_AUTHORITY_CONTENT_BYTES,
        f"{label} exceeds the whole-store canonical byte ceiling",
    )
    return encoded


FAULT_CUTS = (
    "AFTER_CONTEXT_CAPTURE",
    "AFTER_OBJECT_STAGE",
    "AFTER_STATE_STAGE",
    "AFTER_SIGNED_BYTES_STAGE",
    "AFTER_BUNDLE_VALIDATION",
    "BEFORE_POINTER_APPLY",
    "AFTER_POINTER_APPLY_BEFORE_ACK",
)


SERVER_RECEIPT_SCHEMAS: dict[str, tuple[str, tuple[str, ...]]] = {
    "OBSERVER_AUTHORIZATION_STATE_GENESIS_FROM_SESSION_CREATION": (
        "ObserverAuthorizationStateCommitReceipt",
        ("ObserverGrantRegistryCommitReceipt",),
    ),
    "ATTACH_NEW_GRANT_LINEAGE": (
        "ObserverAuthorizationStateCommitReceipt",
        ("ObserverGrantRegistryCommitReceipt", "ObserverGrant"),
    ),
    "ACTIVATE_PENDING_GRANT": (
        "ObserverAuthorizationStateCommitReceipt",
        (
            "ObserverGrantRegistryCommitReceipt",
            "ObserverGrantBoundaryInstallationSetReceipt",
            "ObserverGrantRegistryActivationEntryProof",
            "ObserverAttached",
        ),
    ),
    "BEGIN_GRANT_RENEWAL": (
        "ObserverAuthorizationStateCommitReceipt",
        (
            "ObserverGrantRegistryCommitReceipt",
            "ObserverGrant",
            "ObserverGrantRenewalPredecessorFenceReceipt",
        ),
    ),
    "TERMINATE_GRANT": (
        "ObserverAuthorizationStateCommitReceipt",
        (
            "ObserverGrantRegistryCommitReceipt",
            "ObserverGrantTerminalTransitionReceipt",
            "ObserverGrantReattachmentPolicyResult",
        ),
    ),
}


def _receipt_schema(
    store_id: str,
    transition_kind: str,
) -> tuple[str, tuple[str, ...]]:
    if store_id == "observer-authorization-server":
        schema = SERVER_RECEIPT_SCHEMAS.get(transition_kind)
    elif store_id.startswith("trusted-delivery-boundary:") and store_id.removeprefix(
        "trusted-delivery-boundary:"
    ):
        schema = BOUNDARY_RECEIPT_SCHEMAS.get(transition_kind)
    else:
        schema = None
    _require(schema is not None, "transition has no closed atomic receipt schema")
    return schema


BOUNDARY_RECEIPT_SCHEMAS: dict[str, tuple[str, tuple[str, ...]]] = {}
CO_COMMITTED_OBJECT_SCHEMAS: dict[str, tuple[str, ...]] = {}


def _co_committed_object_schema(
    store_id: str,
    transition_kind: str,
) -> tuple[str, ...]:
    _receipt_schema(store_id, transition_kind)
    return CO_COMMITTED_OBJECT_SCHEMAS.get(transition_kind, ())


def _validate_atomic_receipt_bundle(
    context: AtomicReceiptContext,
    bundle: AtomicReceiptBundle,
) -> None:
    generic = bundle.generic_commit_payload
    selector = bundle.selector
    generic_type_id, generic_snapshot = _artifact_field_snapshot(generic)
    selector_type_id, selector_snapshot = _artifact_field_snapshot(selector)
    generic_values = dict(generic_snapshot)
    selector_values = dict(selector_snapshot)
    _require(
        generic_values.get("transition_kind") == context.transition_kind,
        "generic commit transition mismatch",
    )
    _require(
        generic_values.get("operation_id") == context.operation_id
        and generic_values.get("operation_commitment_digest")
        == context.operation_commitment_digest,
        "generic commit operation commitment mismatch",
    )
    _require(
        generic_values.get("prior_outer_head_digest", object())
        == context.prior_state_digest,
        "generic commit prior-state mismatch",
    )
    _require(
        generic_values.get("installed_outer_head_digest")
        == context.installed_state_digest,
        "generic commit installed-state mismatch",
    )
    _require(
        generic_values.get("installed_selector_version") == context.selector_version,
        "generic commit selector-version mismatch",
    )
    _require(
        generic_values.get("deadline_intent_set_digest")
        == (
            _intent_set_digest(context.deadline_intents)
            if context.deadline_intents
            else None
        ),
        "generic commit intent-set mismatch",
    )
    _require(
        generic_values.get("deadline_conditions", ()) == context.deadline_conditions,
        "generic commit deadline-evaluation mismatch",
    )
    _require(
        selector_values.get("selector_version") == context.selector_version,
        "selector version mismatch",
    )
    _require(
        selector_values.get("selected_head_digest") == context.installed_state_digest,
        "selector does not select the installed state",
    )
    _require(
        selector_values.get("generic_commit_receipt_digest") == _digest(generic),
        "selector does not bind the generic commit",
    )
    selector_digest = _digest(selector)
    generic_digest = _digest(generic)
    for payload in bundle.specialized_payloads:
        payload_type_id, payload_snapshot = _artifact_field_snapshot(payload)
        payload_values = dict(payload_snapshot)
        if "operation_id" in payload_values:
            _require(
                payload_values["operation_id"] == context.operation_id,
                f"{payload_type_id} operation mismatch",
            )
        if "operation_commitment_digest" in payload_values:
            _require(
                payload_values["operation_commitment_digest"]
                == context.operation_commitment_digest,
                f"{payload_type_id} operation commitment mismatch",
            )
        if "installed_selector_version" in payload_values:
            _require(
                payload_values["installed_selector_version"]
                == context.selector_version,
                f"{payload_type_id} selector version mismatch",
            )
        if "installed_selector_digest" in payload_values:
            _require(
                payload_values["installed_selector_digest"] == selector_digest,
                f"{payload_type_id} selector digest mismatch",
            )
        if "outer_commit_receipt_digest" in payload_values:
            _require(
                payload_values["outer_commit_receipt_digest"] == generic_digest,
                f"{payload_type_id} generic commit mismatch",
            )
        if "installed_outer_head_digest" in payload_values:
            _require(
                payload_values["installed_outer_head_digest"]
                == context.installed_state_digest,
                f"{payload_type_id} installed state mismatch",
            )
        if "prior_outer_head_digest" in payload_values:
            _require(
                payload_values["prior_outer_head_digest"] == context.prior_state_digest,
                f"{payload_type_id} prior state mismatch",
            )
        if "deadline_conditions" in payload_values:
            _require(
                payload_values["deadline_conditions"] == context.deadline_conditions,
                f"{payload_type_id} deadline evaluations mismatch",
            )


_PERSISTENCE_ROOT_PREFIX = b"NCP-B01-AUTHORITY-PERSISTENCE-ROOT-V1\x00"
_COUNTERFACTUAL_ENROLLMENT_CAPABILITY = object()
_STORE_ENROLLMENT_CAPABILITY = object()


def _authority_snapshot_persistence_root(
    snapshot: ImmutableAuthoritySnapshot,
    *,
    validation_complete: bool = False,
) -> str:
    """Commit one validated snapshot without serializing its aggregate graph."""

    if not validation_complete:
        _validate_atomic_snapshot(snapshot)
    content = _tuple_map(snapshot.content_bytes)
    digest = hashlib.sha256()
    digest.update(_PERSISTENCE_ROOT_PREFIX)

    def frame(label: bytes, payload: bytes) -> None:
        _require(
            type(label) is bytes
            and 0 < len(label) <= 64
            and type(payload) is bytes
            and len(payload) <= MAX_AUTHORITY_CONTENT_BYTES,
            "persistence-root frame is outside its resource bound",
        )
        digest.update(len(label).to_bytes(2, "big"))
        digest.update(label)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)

    def text(label: bytes, value: str) -> None:
        _bounded_utf8_octets(
            value,
            maximum=MAX_CANONICAL_STRING_CHARS,
            label="persistence-root text",
        )
        frame(label, value.encode("utf-8"))

    def integer(label: bytes, value: int) -> None:
        _require(_safe_int(value), "persistence-root integer is unsafe")
        frame(label, str(value).encode("ascii"))

    text(b"store", snapshot.store_id)
    text(b"authority", snapshot.authority_principal)
    text(b"key", snapshot.authority_key_id)
    text(b"security", snapshot.security_state_digest)
    text(b"clock", snapshot.clock_incarnation)
    integer(b"version", snapshot.snapshot_version)
    frame(
        b"state",
        (
            b"\x00"
            if snapshot.state_digest is None
            else b"\x01" + snapshot.state_digest.encode("ascii")
        ),
    )
    for key, value in snapshot.objects:
        text(b"object-key", key)
        text(b"object-type", _artifact_type_id(value))
        object_bytes = content.get(key)
        _require(
            type(object_bytes) is bytes,
            "persistence-root object lacks canonical content bytes",
        )
        frame(b"object-content-sha256", hashlib.sha256(object_bytes).digest())
        integer(b"object-content-length", len(object_bytes))
    for key, value in snapshot.signed_bytes:
        text(b"signed-key", key)
        frame(b"signed-content-sha256", hashlib.sha256(value).digest())
        integer(b"signed-content-length", len(value))
    for transition in snapshot.transitions:
        text(b"transition", _digest(transition))
    for label, values in (
        (b"state-incarnation", snapshot.used_state_incarnations),
        (b"clock-incarnation", snapshot.used_clock_incarnations),
        (b"signing-key", snapshot.used_signing_keys),
        (b"retired-key", snapshot.retired_signing_keys),
    ):
        for value in values:
            text(label, value)
    for incarnation, high_watermark in snapshot.clock_sample_high_watermarks:
        text(b"high-watermark-clock", incarnation)
        integer(b"high-watermark-value", high_watermark)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class _SyntheticRecoveryAdmission:
    """One-use, in-process recovery authority bound to one durable root."""

    _coordinator: SyntheticAuthorityPersistenceCoordinator
    _capability: object
    snapshot_root: str
    snapshot_version: int
    recovery_id: str
    recovery_sequence: int
    writer_epoch: int
    trusted_recovery_clock_sample: int
    writer_exclusive_not_after: int
    _trusted_clock_source: Callable[[], int] | None
    clock_source_policy: str


@dataclass(frozen=True, slots=True)
class _SyntheticRecoveryAuthority:
    """Opaque authority that can admit the coordinator's current durable root."""

    _coordinator: SyntheticAuthorityPersistenceCoordinator
    _capability: object

    def issue_admission(
        self,
        *,
        trusted_recovery_clock_sample: int,
        writer_exclusive_not_after: int,
        trusted_clock_source: Callable[[], int] | None = None,
    ) -> _SyntheticRecoveryAdmission:
        return self._coordinator.issue_recovery_admission(
            self,
            trusted_recovery_clock_sample=trusted_recovery_clock_sample,
            writer_exclusive_not_after=writer_exclusive_not_after,
            trusted_clock_source=trusted_clock_source,
        )


class SyntheticAuthorityPersistenceCoordinator:
    """Synthetic durable CAS, clock, lease, and single-writer authority."""

    def __init__(
        self,
        snapshot: ImmutableAuthoritySnapshot,
        *,
        trusted_clock_source: Callable[[], int] | None,
        writer_exclusive_not_after: int,
        _counterfactual_capability: object | None = None,
    ) -> None:
        _validate_atomic_snapshot(snapshot)
        _require(
            snapshot.snapshot_version == 0
            or _counterfactual_capability is _COUNTERFACTUAL_ENROLLMENT_CAPABILITY,
            "non-genesis persistence enrollment is test-only and not recovery",
        )
        durable_sample = _tuple_map(snapshot.clock_sample_high_watermarks).get(
            snapshot.clock_incarnation
        )
        _require(
            _safe_int(durable_sample)
            and _safe_int(writer_exclusive_not_after)
            and durable_sample < writer_exclusive_not_after,
            "initial writer lease does not strictly follow durable clock state",
        )
        _require(
            writer_exclusive_not_after - durable_sample
            <= MAX_SYNTHETIC_WRITER_LEASE_DURATION,
            "initial writer lease exceeds the closed maximum duration",
        )
        self._lock = threading.RLock()
        self._snapshot = snapshot
        self._snapshot_root = _authority_snapshot_persistence_root(
            snapshot,
            validation_complete=True,
        )
        self._identity = (
            snapshot.store_id,
            snapshot.authority_principal,
        )
        self._trusted_clock_source = trusted_clock_source
        self._trusted_clock_sample = durable_sample
        self._writer_epoch = 1
        self._writer_capability = object()
        self._writer_exclusive_not_after = writer_exclusive_not_after
        self._recovery_capability = object()
        self._pending_recovery_admission: _SyntheticRecoveryAdmission | None = None
        self._recovery_authority_capability = object()
        self._next_recovery_sequence = 1
        self._transport_enqueues: dict[
            str,
            tuple[_SyntheticExternalTransportEnqueueRecord, bytes],
        ] = {}
        self._recovery_authority = _SyntheticRecoveryAuthority(
            _coordinator=self,
            _capability=self._recovery_authority_capability,
        )

    def _bind_initial(self, store: AtomicAuthorityStore) -> None:
        store._bind_coordinator_state(
            coordinator=self,
            snapshot=self._snapshot,
            snapshot_root=self._snapshot_root,
            writer_epoch=self._writer_epoch,
            writer_capability=self._writer_capability,
            writer_exclusive_not_after=self._writer_exclusive_not_after,
            trusted_clock_sample=self._trusted_clock_sample,
        )

    def issue_recovery_admission(
        self,
        authority: _SyntheticRecoveryAuthority,
        *,
        trusted_recovery_clock_sample: int,
        writer_exclusive_not_after: int,
        trusted_clock_source: Callable[[], int] | None,
    ) -> _SyntheticRecoveryAdmission:
        with self._lock:
            _require(
                type(authority) is _SyntheticRecoveryAuthority
                and authority._coordinator is self
                and authority._capability is self._recovery_authority_capability,
                "recovery authority is forged or foreign",
            )
            durable_sample = _tuple_map(
                self._snapshot.clock_sample_high_watermarks
            ).get(self._snapshot.clock_incarnation)
            _require(
                _safe_int(trusted_recovery_clock_sample)
                and _safe_int(durable_sample)
                and trusted_recovery_clock_sample >= durable_sample
                and trusted_recovery_clock_sample >= self._trusted_clock_sample
                and _safe_int(writer_exclusive_not_after)
                and trusted_recovery_clock_sample < writer_exclusive_not_after
                and writer_exclusive_not_after - trusted_recovery_clock_sample
                <= MAX_SYNTHETIC_WRITER_LEASE_DURATION,
                "recovery authority proposed rollback or an excessive writer lease",
            )
            _require(
                _safe_int(self._next_recovery_sequence)
                and self._next_recovery_sequence < MAX_SAFE_INTEGER
                and _safe_int(self._writer_epoch)
                and self._writer_epoch < MAX_SAFE_INTEGER,
                "recovery sequence or writer epoch capacity is exhausted",
            )
            recovery_sequence = self._next_recovery_sequence
            recovery_id = _uuid_for(
                (
                    "authority-recovery",
                    self._identity,
                    self._snapshot_root,
                    recovery_sequence,
                )
            )
            admission_capability = object()
            self._recovery_capability = admission_capability
            admission = _SyntheticRecoveryAdmission(
                _coordinator=self,
                _capability=admission_capability,
                snapshot_root=self._snapshot_root,
                snapshot_version=self._snapshot.snapshot_version,
                recovery_id=recovery_id,
                recovery_sequence=recovery_sequence,
                writer_epoch=self._writer_epoch + 1,
                trusted_recovery_clock_sample=trusted_recovery_clock_sample,
                writer_exclusive_not_after=writer_exclusive_not_after,
                _trusted_clock_source=trusted_clock_source,
                clock_source_policy=(
                    "FIXTURE_EXPLICIT_INJECTION_ONLY"
                    if trusted_clock_source is None
                    else "SYNTHETIC_IN_PROCESS_MONOTONIC_CALLBACK"
                ),
            )
            self._pending_recovery_admission = admission
            return admission

    def recover(
        self,
        snapshot: ImmutableAuthoritySnapshot,
        *,
        admission: _SyntheticRecoveryAdmission,
    ) -> AtomicAuthorityStore:
        with self._lock:
            _require(
                type(admission) is _SyntheticRecoveryAdmission
                and admission is self._pending_recovery_admission
                and admission._coordinator is self
                and admission._capability is self._recovery_capability
                and admission.snapshot_root == self._snapshot_root
                and admission.snapshot_version == self._snapshot.snapshot_version,
                "recovery admission is forged, stale, foreign, or already consumed",
            )
            _require(
                admission.recovery_sequence == self._next_recovery_sequence
                and admission.writer_epoch == self._writer_epoch + 1
                and admission.recovery_id
                == _uuid_for(
                    (
                        "authority-recovery",
                        self._identity,
                        self._snapshot_root,
                        self._next_recovery_sequence,
                    )
                )
                and admission.clock_source_policy
                == (
                    "FIXTURE_EXPLICIT_INJECTION_ONLY"
                    if admission._trusted_clock_source is None
                    else "SYNTHETIC_IN_PROCESS_MONOTONIC_CALLBACK"
                ),
                "recovery admission epoch, sequence, ID, or clock policy drifted",
            )
            _validate_atomic_snapshot(snapshot)
            candidate_root = _authority_snapshot_persistence_root(
                snapshot,
                validation_complete=True,
            )
            _require(
                candidate_root == self._snapshot_root and snapshot == self._snapshot,
                "recovery snapshot is not the coordinator's exact durable state",
            )
            durable_sample = _tuple_map(snapshot.clock_sample_high_watermarks).get(
                snapshot.clock_incarnation
            )
            _require(
                _safe_int(admission.trusted_recovery_clock_sample)
                and _safe_int(durable_sample)
                and admission.trusted_recovery_clock_sample >= durable_sample
                and admission.trusted_recovery_clock_sample
                >= self._trusted_clock_sample,
                "trusted recovery clock does not continue durable monotonic state",
            )
            _require(
                _safe_int(admission.writer_exclusive_not_after)
                and admission.trusted_recovery_clock_sample
                < admission.writer_exclusive_not_after
                and admission.writer_exclusive_not_after
                - admission.trusted_recovery_clock_sample
                <= MAX_SYNTHETIC_WRITER_LEASE_DURATION,
                "recovered writer lease is expired or unbounded",
            )
            self._trusted_clock_source = admission._trusted_clock_source
            self._trusted_clock_sample = admission.trusted_recovery_clock_sample
            self._writer_epoch += 1
            _require(
                self._writer_epoch == admission.writer_epoch,
                "recovered writer epoch did not match its admission",
            )
            self._writer_capability = object()
            self._writer_exclusive_not_after = admission.writer_exclusive_not_after
            self._recovery_capability = object()
            self._pending_recovery_admission = None
            self._next_recovery_sequence = _checked_add(
                self._next_recovery_sequence,
                1,
            )
            recovered = AtomicAuthorityStore.__new__(AtomicAuthorityStore)
            self._bind_initial(recovered)
            return recovered

    def _require_current_writer_locked(
        self,
        writer: AtomicAuthorityStore,
    ) -> None:
        _require(
            type(writer) is AtomicAuthorityStore
            and writer._coordinator is self
            and writer._writer_epoch == self._writer_epoch
            and writer._writer_capability is self._writer_capability,
            "authority writer is stale, foreign, or revoked",
        )
        _require(
            writer._snapshot_root == self._snapshot_root
            and writer._snapshot is self._snapshot,
            "authority writer cache is stale or belongs to a sibling root",
        )

    def _observe_clock_locked(
        self,
        writer: AtomicAuthorityStore,
        sample: int,
    ) -> None:
        self._require_current_writer_locked(writer)
        _require(_safe_int(sample), "unsafe trusted clock sample")
        durable_sample = _tuple_map(self._snapshot.clock_sample_high_watermarks).get(
            self._snapshot.clock_incarnation
        )
        _require(
            _safe_int(durable_sample)
            and sample >= durable_sample
            and sample >= self._trusted_clock_sample
            and sample < self._writer_exclusive_not_after,
            "trusted clock rolled back or reached the writer's exclusive lease",
        )
        self._trusted_clock_sample = sample
        writer._trusted_clock_sample = sample

    def commit(
        self,
        writer: AtomicAuthorityStore,
        candidate: AtomicCandidate,
        *,
        injected_clock_sample: int | None,
        fault_cut: str | None,
    ) -> AtomicTransitionRecord:
        with self._lock:
            self._require_current_writer_locked(writer)
            if injected_clock_sample is None:
                _require(
                    self._trusted_clock_source is not None,
                    "authority coordinator lacks a trusted clock source",
                )
                sample = self._trusted_clock_source()
            else:
                sample = injected_clock_sample
            self._observe_clock_locked(writer, sample)
            return writer._commit_locked(
                candidate,
                trusted_clock_sample=sample,
                fault_cut=fault_cut,
            )

    def install_locked(
        self,
        writer: AtomicAuthorityStore,
        *,
        expected_snapshot: ImmutableAuthoritySnapshot,
        expected_snapshot_root: str,
        next_snapshot: ImmutableAuthoritySnapshot,
    ) -> str:
        self._require_current_writer_locked(writer)
        _require(
            expected_snapshot is self._snapshot
            and expected_snapshot_root == self._snapshot_root,
            "durable snapshot CAS base is stale or substituted",
        )
        next_root = _authority_snapshot_persistence_root(
            next_snapshot,
            validation_complete=True,
        )
        self._snapshot = next_snapshot
        self._snapshot_root = next_root
        self._recovery_capability = object()
        self._pending_recovery_admission = None
        return next_root

    def enqueue_external_transport(
        self,
        writer: AtomicAuthorityStore,
        *,
        fact: TrustedDeliveryExternalTransportDrainFact,
        exact_payload: bytes,
        trusted_clock_sample: int,
    ) -> _SyntheticExternalTransportEnqueueRecord:
        """Linearize one synthetic physical enqueue against the live gate."""

        with self._lock:
            self._require_current_writer_locked(writer)
            self._observe_clock_locked(writer, trusted_clock_sample)
            _require(
                type(fact) is TrustedDeliveryExternalTransportDrainFact
                and type(exact_payload) is bytes
                and 0 < len(exact_payload) <= MAX_AUTHORITY_CONTENT_BYTES,
                "transport enqueue fact or payload is outside its exact bound",
            )
            snapshot = self._snapshot
            state = snapshot.state
            _require(
                type(state) is TrustedDeliveryReleaseStateHead
                and snapshot.store_id.startswith("trusted-delivery-boundary:"),
                "transport enqueue did not target one boundary authority",
            )
            objects = _tuple_map(snapshot.objects)
            fact_digest = _digest(fact)
            _require(
                objects.get(fact_digest) == fact
                and _tuple_map(state.drain_facts).get(fact.attempt_identity)
                == fact_digest,
                "transport enqueue attempt is not the exact live durable fact",
            )
            grant_map = objects.get(state.grant_map_head_digest)
            _require(
                type(grant_map) is TrustedDeliveryBoundaryGrantMapHead,
                "transport enqueue live grant map is absent",
            )
            entry = objects.get(
                _tuple_map(grant_map.entries).get(
                    _digest(fact.full_boundary_key),
                    "",
                )
            )
            outbox = objects.get(fact.exact_outbox_item_digest)
            _require(
                type(entry) is TrustedDeliveryBoundaryGrantStateHead
                and entry.phase == "LIVE_BOUNDARY_GRANT"
                and fact_digest in entry.active_drain_fact_digests
                and type(outbox) is TrustedDeliveryReleaseOutbox,
                "terminal or stale grant state fenced the physical enqueue",
            )
            dispatch = fact.dispatch_context
            _require(
                type(dispatch) is SyntheticAuthenticatedDispatchContext,
                "transport enqueue dispatch context type drifted",
            )
            destination_cut = fact.expected_dispatch_destination_cut
            _require(
                type(destination_cut) is ExpectedDispatchDestinationCut
                and dispatch.destination_cut_digest
                == dispatch_destination_cut_digest(destination_cut)
                and (
                    dispatch.transport_gate_state_digest,
                    dispatch.transport_gate_epoch,
                )
                == (
                    destination_cut.transport_gate_state_digest,
                    destination_cut.transport_gate_epoch,
                )
                and destination_cut.transport_gate_state_digest
                == dispatch_transport_gate_state_digest(destination_cut),
                "transport enqueue destination or derived gate cut drifted",
            )
            _require(
                snapshot.snapshot_version == dispatch.transport_gate_epoch + 1,
                "transport enqueue gate epoch is stale or future",
            )
            _require(
                state.security_state_digest == dispatch.local_security_state_digest,
                "transport enqueue security state drifted",
            )
            _require(
                state.boundary_clock_incarnation == dispatch.boundary_clock_incarnation,
                "transport enqueue clock incarnation drifted",
            )
            _require(
                trusted_clock_sample >= dispatch.verified_at
                and trusted_clock_sample < dispatch.exclusive_not_after,
                "transport enqueue is outside its strict dispatch interval",
            )
            _require(
                exact_payload == fact.actual_dispatch_payload == outbox.complete_payload
                and hashlib.sha256(exact_payload).hexdigest() == outbox.payload_digest,
                "transport enqueue exact bytes drifted",
            )
            _require(
                fact.attempt_identity not in self._transport_enqueues
                and len(self._transport_enqueues) < MAX_ATTEMPTS
                and sum(
                    len(payload)
                    for _record, payload in self._transport_enqueues.values()
                )
                + len(exact_payload)
                <= MAX_AUTHORITY_CONTENT_BYTES,
                "transport enqueue is replayed or exceeds its queue bound",
            )
            record = _SyntheticExternalTransportEnqueueRecord(
                attempt_identity=fact.attempt_identity,
                drain_fact_digest=fact_digest,
                persistence_root=self._snapshot_root,
                snapshot_version=snapshot.snapshot_version,
                writer_epoch=self._writer_epoch,
                writer_exclusive_not_after=self._writer_exclusive_not_after,
                transport_gate_epoch=dispatch.transport_gate_epoch,
                transport_gate_state_digest=dispatch.transport_gate_state_digest,
                boundary_clock_incarnation=state.boundary_clock_incarnation,
                enqueue_clock_sample=trusted_clock_sample,
                payload_digest=hashlib.sha256(exact_payload).hexdigest(),
                payload_length=len(exact_payload),
                destination_cut_digest=dispatch.destination_cut_digest,
                queue_sequence=len(self._transport_enqueues) + 1,
            )
            self._transport_enqueues[fact.attempt_identity] = (
                record,
                exact_payload,
            )
            return record

    def require_external_transport_enqueue(
        self,
        writer: AtomicAuthorityStore,
        fact: TrustedDeliveryExternalTransportDrainFact,
    ) -> _SyntheticExternalTransportEnqueueRecord:
        with self._lock:
            self._require_current_writer_locked(writer)
            item = self._transport_enqueues.get(fact.attempt_identity)
            _require(
                item is not None
                and item[0].drain_fact_digest == _digest(fact)
                and item[1] == fact.actual_dispatch_payload,
                "drain resolution lacks the exact synthetic physical enqueue",
            )
            return item[0]


class AtomicAuthorityStore:
    """One authority whose complete durable state is one immutable snapshot."""

    def __init__(
        self,
        *,
        store_id: str,
        authority_principal: str,
        authority_key_id: str,
        security_state_digest: str,
        clock_incarnation: str,
        writer_exclusive_not_after: int,
        trusted_clock_source: Callable[[], int] | None = None,
        _enrollment_capability: object | None = None,
    ) -> None:
        _require(
            _enrollment_capability is _STORE_ENROLLMENT_CAPABILITY,
            "authority stores must be created by the enrollment factory",
        )
        snapshot = ImmutableAuthoritySnapshot(
            store_id=store_id,
            authority_principal=authority_principal,
            authority_key_id=authority_key_id,
            security_state_digest=security_state_digest,
            clock_incarnation=clock_incarnation,
            snapshot_version=0,
            state=None,
            state_digest=None,
            objects=(),
            content_bytes=(),
            signed_bytes=(),
            transitions=(),
            used_state_incarnations=(),
            used_clock_incarnations=(clock_incarnation,),
            used_signing_keys=(authority_key_id,),
            retired_signing_keys=(),
            clock_sample_high_watermarks=((clock_incarnation, 0),),
        )
        coordinator = SyntheticAuthorityPersistenceCoordinator(
            snapshot,
            trusted_clock_source=trusted_clock_source,
            writer_exclusive_not_after=writer_exclusive_not_after,
        )
        coordinator._bind_initial(self)

    @classmethod
    def enroll(
        cls,
        *,
        store_id: str,
        authority_principal: str,
        authority_key_id: str,
        security_state_digest: str,
        clock_incarnation: str,
        writer_exclusive_not_after: int,
        trusted_clock_source: Callable[[], int] | None = None,
    ) -> tuple[AtomicAuthorityStore, _SyntheticRecoveryAuthority]:
        store = cls(
            store_id=store_id,
            authority_principal=authority_principal,
            authority_key_id=authority_key_id,
            security_state_digest=security_state_digest,
            clock_incarnation=clock_incarnation,
            writer_exclusive_not_after=writer_exclusive_not_after,
            trusted_clock_source=trusted_clock_source,
            _enrollment_capability=_STORE_ENROLLMENT_CAPABILITY,
        )
        return store, store._coordinator._recovery_authority

    def _bind_coordinator_state(
        self,
        *,
        coordinator: SyntheticAuthorityPersistenceCoordinator,
        snapshot: ImmutableAuthoritySnapshot,
        snapshot_root: str,
        writer_epoch: int,
        writer_capability: object,
        writer_exclusive_not_after: int,
        trusted_clock_sample: int,
    ) -> None:
        self._coordinator = coordinator
        self._snapshot = snapshot
        self._snapshot_root = snapshot_root
        self._writer_epoch = writer_epoch
        self._writer_capability = writer_capability
        self._writer_exclusive_not_after = writer_exclusive_not_after
        self._trusted_clock_sample = trusted_clock_sample
        self._building_receipts = False

    @classmethod
    def recover(
        cls,
        snapshot: ImmutableAuthoritySnapshot,
        *,
        admission: _SyntheticRecoveryAdmission,
    ) -> AtomicAuthorityStore:
        _require(
            type(admission) is _SyntheticRecoveryAdmission,
            "recovery requires an exact coordinator-issued admission",
        )
        return admission._coordinator.recover(
            snapshot,
            admission=admission,
        )

    @classmethod
    def _from_validated_counterfactual_snapshot_for_test(
        cls,
        snapshot: ImmutableAuthoritySnapshot,
        *,
        trusted_clock_sample: int,
        writer_exclusive_not_after: int = 10_000,
    ) -> AtomicAuthorityStore:
        """Create an isolated model branch; this is intentionally not recovery."""

        store, _authority = cls._enroll_validated_counterfactual_snapshot_for_test(
            snapshot,
            trusted_clock_sample=trusted_clock_sample,
            writer_exclusive_not_after=writer_exclusive_not_after,
        )
        return store

    @classmethod
    def _enroll_validated_counterfactual_snapshot_for_test(
        cls,
        snapshot: ImmutableAuthoritySnapshot,
        *,
        trusted_clock_sample: int,
        writer_exclusive_not_after: int = 10_000,
    ) -> tuple[AtomicAuthorityStore, _SyntheticRecoveryAuthority]:
        """Enroll one isolated model branch and return its external test authority."""

        _preflight_atomic_snapshot(snapshot)
        durable_sample = _tuple_map(snapshot.clock_sample_high_watermarks).get(
            snapshot.clock_incarnation
        )
        _require(
            durable_sample is not None
            and _safe_int(trusted_clock_sample)
            and trusted_clock_sample >= durable_sample
            and trusted_clock_sample < writer_exclusive_not_after
            and writer_exclusive_not_after - trusted_clock_sample
            <= MAX_SYNTHETIC_WRITER_LEASE_DURATION,
            "counterfactual clock does not continue the branch snapshot",
        )
        _validate_atomic_snapshot(snapshot, preflight_complete=True)
        coordinator = SyntheticAuthorityPersistenceCoordinator(
            snapshot,
            trusted_clock_source=None,
            writer_exclusive_not_after=writer_exclusive_not_after,
            _counterfactual_capability=_COUNTERFACTUAL_ENROLLMENT_CAPABILITY,
        )
        coordinator._trusted_clock_sample = trusted_clock_sample
        store = cls.__new__(cls)
        coordinator._bind_initial(store)
        return store, coordinator._recovery_authority

    @property
    def snapshot(self) -> ImmutableAuthoritySnapshot:
        return self._snapshot

    @property
    def persistence_root(self) -> str:
        return self._snapshot_root

    def object(self, digest: str, expected_type: type[T]) -> T:
        value = _tuple_map(self._snapshot.objects).get(digest)
        _require(type(value) is expected_type, f"missing {expected_type.__name__}")
        return value

    def recover_exact_signed_bytes(self, payload_digest: str) -> bytes:
        blob = _tuple_map(self._snapshot.signed_bytes).get(payload_digest)
        _require(blob is not None, "exact signed receipt bytes are unavailable")
        return blob

    def enqueue_external_transport_for_test(
        self,
        *,
        fact: TrustedDeliveryExternalTransportDrainFact,
        exact_payload: bytes,
        trusted_clock_sample: int,
    ) -> _SyntheticExternalTransportEnqueueRecord:
        return self._coordinator.enqueue_external_transport(
            self,
            fact=fact,
            exact_payload=exact_payload,
            trusted_clock_sample=trusted_clock_sample,
        )

    def require_external_transport_enqueue_for_test(
        self,
        fact: TrustedDeliveryExternalTransportDrainFact,
    ) -> _SyntheticExternalTransportEnqueueRecord:
        return self._coordinator.require_external_transport_enqueue(self, fact)

    def set_trusted_clock_for_test(self, sample: int) -> None:
        """Advance the synthetic trusted clock; production code has no setter."""
        with self._coordinator._lock:
            self._coordinator._observe_clock_locked(self, sample)

    def transition_for_operation(
        self,
        operation_id: str,
    ) -> AtomicTransitionRecord | None:
        matches = [
            item
            for item in self._snapshot.transitions
            if item.operation_id == operation_id
        ]
        _require(len(matches) <= 1, "operation installed more than once")
        return matches[0] if matches else None

    def commit(
        self,
        candidate: AtomicCandidate,
        *,
        fault_cut: str | None = None,
    ) -> AtomicTransitionRecord:
        """Commit using only the store-owned clock source sampled under the lock."""

        _require(
            not self._building_receipts,
            "receipt builder cannot reenter authority-store mutation",
        )
        return self._coordinator.commit(
            self,
            candidate,
            injected_clock_sample=None,
            fault_cut=fault_cut,
        )

    def commit_at_for_test(
        self,
        candidate: AtomicCandidate,
        *,
        trusted_clock_sample: int,
        fault_cut: str | None = None,
    ) -> AtomicTransitionRecord:
        """Fixture-only atomic injection; production callers use ``commit``."""

        _require(
            not self._building_receipts,
            "receipt builder cannot reenter authority-store mutation",
        )
        return self._coordinator.commit(
            self,
            candidate,
            injected_clock_sample=trusted_clock_sample,
            fault_cut=fault_cut,
        )

    def _commit_locked(
        self,
        candidate: AtomicCandidate,
        *,
        trusted_clock_sample: int,
        fault_cut: str | None = None,
    ) -> AtomicTransitionRecord:
        base = self._snapshot

        def cut(name: str) -> None:
            if fault_cut == name:
                raise ProbeError(f"simulated atomic fault cut: {name}")

        _require(
            type(candidate) is AtomicCandidate, "atomic candidate type is not exact"
        )
        _require(
            type(candidate.objects) is tuple
            and len(candidate.objects) <= MAX_ITEMS
            and type(candidate.deadline_intents) is tuple
            and len(candidate.deadline_intents) <= MAX_ITEMS,
            "atomic candidate collection shape is outside its bound",
        )
        _assert_deeply_immutable(candidate.state)
        for value in candidate.objects:
            _assert_deeply_immutable(value)
        for intent in candidate.deadline_intents:
            _assert_deeply_immutable(intent)
        _preflight_stored_value_group(
            (
                candidate.state,
                *candidate.objects,
                *candidate.deadline_intents,
            ),
            label="atomic candidate",
        )
        _require(bool(candidate.operation_id), "atomic operation identity is empty")
        prior_operation = self.transition_for_operation(candidate.operation_id)
        operation_commitment = _candidate_operation_commitment(
            candidate,
            store_id=base.store_id,
            authority_principal=base.authority_principal,
        )
        _canonical_stored_bytes(operation_commitment)
        operation_commitment_digest = _digest(operation_commitment)
        if prior_operation is not None:
            _require(
                prior_operation.operation_commitment_digest
                == operation_commitment_digest,
                "operation identity was reused with different canonical intent",
            )
            return prior_operation
        _require(
            len(base.transitions) < MAX_AUTHORITY_TRANSITIONS,
            "authority transition capacity exhausted; retire generation",
        )
        _require(
            candidate.expected_snapshot_version == base.snapshot_version,
            "stale atomic transaction context",
        )
        _require(
            candidate.expected_state_digest == base.state_digest,
            "stale or sibling prior state",
        )
        commit_time = trusted_clock_sample
        high_watermarks = _tuple_map(base.clock_sample_high_watermarks)
        _require(
            commit_time == self._trusted_clock_sample
            and commit_time >= high_watermarks.get(base.clock_incarnation, 0),
            "commit clock observation is not the locked trusted sample",
        )
        if candidate.allocate_state_incarnation is not None:
            _require(
                candidate.allocate_state_incarnation
                not in base.used_state_incarnations,
                "state incarnation was already used",
            )
            _require(base.state is None, "genesis cannot reset an initialized store")
        allocations = tuple(
            item
            for item in candidate.objects
            if isinstance(item, ParentSelectorAllocationReceipt)
        )
        if base.state is None:
            _require(
                candidate.allocate_state_incarnation is not None
                and bool(candidate.allocate_state_incarnation),
                "genesis lacks one never-used state incarnation",
            )
            _require(len(allocations) == 1, "genesis lacks one parent allocation")
            _validate_parent_allocation(
                allocations[0],
                store_id=base.store_id,
                state_incarnation=candidate.allocate_state_incarnation,
            )
        else:
            _require(
                candidate.allocate_state_incarnation is None and not allocations,
                "non-genesis transaction carries a parent allocation",
            )
        _require(
            candidate.next_clock_incarnation is None,
            "this closed probe has no authenticated clock-restart transition",
        )
        _require(
            candidate.next_authority_key_id is None
            and candidate.next_security_state_digest is None,
            "this closed probe has no authority-security rotation transition",
        )
        intents = candidate.deadline_intents
        intent_keys = [
            (
                item.purpose,
                item.deadline_kind,
                item.operation_id,
            )
            for item in intents
        ]
        _require(
            intent_keys == sorted(intent_keys),
            "deadline intent set is not canonical",
        )
        _require(len(set(intent_keys)) == len(intent_keys), "duplicate intent")
        for intent in intents:
            _require(intent.store_id == base.store_id, "intent store mismatch")
            _require(
                intent.authority_principal == base.authority_principal,
                "intent authority mismatch",
            )
            _require(
                intent.transition_kind == candidate.transition_kind,
                "intent transition mismatch",
            )
            _require(
                intent.operation_id == candidate.operation_id,
                "intent operation mismatch",
            )
            _require(
                intent.expected_prior_state_digest == base.state_digest,
                "intent prior-state mismatch",
            )
            _require(
                intent.expected_prior_selector_version == base.snapshot_version,
                "intent selector version mismatch",
            )
            _require(
                intent.security_state_digest == base.security_state_digest,
                "intent security state mismatch",
            )
            _require(
                intent.clock_incarnation == base.clock_incarnation,
                "intent clock incarnation mismatch",
            )
            _require(
                intent.authorization_linearization_mode
                == "TRANSACTION_MANAGER_LINEARIZATION"
                and intent.qualified_completion_bound == 0
                and intent.qualified_effective_deadline_margin == 0
                and intent.timing_qualification_digest is None
                and intent.transaction_manager_guarantee
                == "CLOCK_PREDICATE_AND_POINTER_APPLY_ONE_LOCK",
                "unsupported timing qualification cannot authorize a transition",
            )
        cut("AFTER_CONTEXT_CAPTURE")

        staged_objects = _tuple_map(base.objects)
        staged_content = _tuple_map(base.content_bytes)
        copied_values = candidate.objects
        copied_state = candidate.state
        staged_values: tuple[Any, ...] = (
            *copied_values,
            copied_state,
            operation_commitment,
            *intents,
        )
        if intents:
            staged_values = (*staged_values, _intent_set_artifact(intents))
        for value in staged_values:
            _assert_deeply_immutable(value)
            value_digest = _digest(value)
            encoded = _canonical_stored_bytes(value)
            prior = staged_content.get(value_digest)
            _require(prior in (None, encoded), "content digest collision")
            staged_objects[value_digest] = value
            staged_content[value_digest] = encoded
        cut("AFTER_OBJECT_STAGE")

        installed_digest = _digest(copied_state)
        _require(
            staged_content[installed_digest] == _canonical_stored_bytes(copied_state),
            "installed state was not staged exactly",
        )
        cut("AFTER_STATE_STAGE")

        evaluations = (
            _evaluate_intents(
                intents,
                commit_time=commit_time,
                installed_successor_digest=installed_digest,
                installed_selector_version=base.snapshot_version + 1,
            )
            if intents
            else ()
        )
        if intents:
            _validate_intent_evaluations(
                intents,
                evaluations,
                installed_successor_digest=installed_digest,
                installed_selector_version=base.snapshot_version + 1,
            )
        context = AtomicReceiptContext(
            store_id=base.store_id,
            authority_principal=base.authority_principal,
            transition_kind=candidate.transition_kind,
            operation_id=candidate.operation_id,
            operation_commitment_digest=operation_commitment_digest,
            prior_state_digest=base.state_digest,
            installed_state_digest=installed_digest,
            selector_version=base.snapshot_version + 1,
            commit_clock_incarnation=base.clock_incarnation,
            exact_commit_time=commit_time,
            signing_key_id=base.authority_key_id,
            security_state_digest=base.security_state_digest,
            deadline_intents=intents,
            deadline_conditions=evaluations,
        )
        self._building_receipts = True
        try:
            bundle = candidate.receipt_builder(context)
        finally:
            self._building_receipts = False
        _require(
            type(bundle) is AtomicReceiptBundle
            and type(bundle.specialized_payloads) is tuple
            and len(bundle.specialized_payloads) <= MAX_ITEMS
            and type(bundle.co_committed_objects) is tuple
            and len(bundle.co_committed_objects) <= MAX_ITEMS,
            "atomic receipt bundle shape is outside its bound",
        )
        _preflight_stored_value_group(
            (
                bundle.generic_commit_payload,
                bundle.selector,
                *bundle.specialized_payloads,
                *bundle.co_committed_objects,
            ),
            label="atomic receipt bundle",
        )
        _assert_deeply_immutable(bundle)
        generic_type, required = _receipt_schema(
            base.store_id,
            candidate.transition_kind,
        )
        _require(
            _artifact_type_id(bundle.generic_commit_payload)
            == _stable_artifact_type_id(generic_type),
            "wrong generic commit type",
        )
        specialized_types = tuple(
            _artifact_type_id(item) for item in bundle.specialized_payloads
        )
        required = tuple(_stable_artifact_type_id(item) for item in required)
        _require(
            specialized_types == required,
            "atomic specialized receipt set is incomplete, extra, or reordered",
        )
        _validate_atomic_receipt_bundle(context, bundle)
        required_co_types = tuple(
            _stable_artifact_type_id(item)
            for item in _co_committed_object_schema(
                base.store_id,
                candidate.transition_kind,
            )
        )
        co_committed_types = tuple(
            _artifact_type_id(item) for item in bundle.co_committed_objects
        )
        _require(
            co_committed_types == required_co_types,
            "co-committed object set is incomplete, extra, or reordered",
        )
        co_committed_digests: list[str] = []
        for value in bundle.co_committed_objects:
            _assert_deeply_immutable(value)
            value_digest = _digest(value)
            encoded = _canonical_stored_bytes(value)
            prior = staged_content.get(value_digest)
            _require(prior in (None, encoded), "co-committed content collision")
            staged_objects[value_digest] = value
            staged_content[value_digest] = encoded
            co_committed_digests.append(value_digest)
        _require(
            len(set(co_committed_digests)) == len(co_committed_digests),
            "duplicate co-committed object",
        )
        _validate_transition_semantics(
            prior_state=base.state,
            installed_state=copied_state,
            staged_objects=staged_objects,
            context=context,
            bundle=bundle,
        )
        selector_digest = _digest(bundle.selector)
        selector_bytes = _canonical_stored_bytes(bundle.selector)
        prior_selector_bytes = staged_content.get(selector_digest)
        _require(
            prior_selector_bytes in (None, selector_bytes),
            "selector content collision",
        )
        staged_objects[selector_digest] = bundle.selector
        staged_content[selector_digest] = selector_bytes
        signed_bytes = _tuple_map(base.signed_bytes)
        signed_types: list[str] = []
        signed_digests: list[str] = []
        signed_seen: set[tuple[str, str]] = set()
        signed_payloads = (
            bundle.generic_commit_payload,
            *bundle.specialized_payloads,
        )
        for payload in signed_payloads:
            payload_digest = _digest(payload)
            artifact, blob = _signed_artifact(
                payload,
                signer_principal=base.authority_principal,
                signing_key_id=base.authority_key_id,
                security_state_digest=base.security_state_digest,
            )
            identity = (artifact.artifact_type, payload_digest)
            _require(identity not in signed_seen, "duplicate receipt in atomic bundle")
            signed_seen.add(identity)
            prior_blob = signed_bytes.get(payload_digest)
            _require(prior_blob in (None, blob), "signed byte collision")
            signed_bytes[payload_digest] = blob
            staged_objects[payload_digest] = payload
            staged_content[payload_digest] = _canonical_stored_bytes(payload)
            signed_types.append(artifact.artifact_type)
            signed_digests.append(payload_digest)
        cut("AFTER_SIGNED_BYTES_STAGE")

        _require(signed_digests, "atomic transaction lacks generic commit")
        generic_digest = signed_digests[0]
        specialized_types = tuple(signed_types[1:])
        specialized_digests = tuple(signed_digests[1:])
        _require(
            specialized_types == required,
            "atomic specialized receipt set is incomplete, extra, or reordered",
        )
        _require(
            len(set(specialized_digests)) == len(specialized_digests),
            "duplicate specialized receipt digest",
        )
        cut("AFTER_BUNDLE_VALIDATION")

        record = AtomicTransitionRecord(
            store_id=base.store_id,
            authority_principal=base.authority_principal,
            transition_kind=candidate.transition_kind,
            operation_id=candidate.operation_id,
            operation_commitment_digest=operation_commitment_digest,
            prior_state_digest=base.state_digest,
            installed_state_digest=installed_digest,
            selector_digest=selector_digest,
            selector_version=base.snapshot_version + 1,
            generic_commit_digest=generic_digest,
            specialized_receipt_digests=specialized_digests,
            specialized_receipt_types=specialized_types,
            required_specialized_receipt_types=required,
            co_committed_object_digests=tuple(co_committed_digests),
            co_committed_object_types=co_committed_types,
            required_co_committed_object_types=required_co_types,
            exact_commit_time=commit_time,
            commit_clock_incarnation=base.clock_incarnation,
            signing_key_id=base.authority_key_id,
            security_state_digest=base.security_state_digest,
            deadline_intent_set_digest=(
                _intent_set_digest(intents) if intents else None
            ),
            deadline_evaluation_set_digest=(
                evaluations[0].evaluation_set_digest if evaluations else None
            ),
        )
        record_digest = _digest(record)
        record_bytes = _canonical_stored_bytes(record)
        prior_record_bytes = staged_content.get(record_digest)
        _require(
            prior_record_bytes in (None, record_bytes),
            "transition-record content collision",
        )
        staged_objects[record_digest] = record
        staged_content[record_digest] = record_bytes
        _require(
            len(staged_objects) <= MAX_AUTHORITY_OBJECTS,
            "authority object capacity exhausted; retire generation",
        )
        _require(
            sum(len(item) for item in staged_content.values())
            <= MAX_AUTHORITY_CONTENT_BYTES,
            "authority content capacity exhausted; retire generation",
        )
        _require(
            sum(len(item) for item in signed_bytes.values())
            <= MAX_AUTHORITY_SIGNED_BYTES,
            "authority signed-byte capacity exhausted; retire generation",
        )
        cut("BEFORE_POINTER_APPLY")

        next_key = (
            base.authority_key_id
            if candidate.next_authority_key_id is None
            else candidate.next_authority_key_id
        )
        retired = base.retired_signing_keys
        if next_key != base.authority_key_id:
            retired = (*retired, base.authority_key_id)
        next_clock = (
            base.clock_incarnation
            if candidate.next_clock_incarnation is None
            else candidate.next_clock_incarnation
        )
        next_high_watermarks = dict(high_watermarks)
        next_high_watermarks[base.clock_incarnation] = commit_time
        if next_clock != base.clock_incarnation:
            next_high_watermarks[next_clock] = 0
        next_snapshot = ImmutableAuthoritySnapshot(
            store_id=base.store_id,
            authority_principal=base.authority_principal,
            authority_key_id=next_key,
            security_state_digest=(
                base.security_state_digest
                if candidate.next_security_state_digest is None
                else candidate.next_security_state_digest
            ),
            clock_incarnation=next_clock,
            snapshot_version=base.snapshot_version + 1,
            state=copied_state,
            state_digest=installed_digest,
            objects=tuple(sorted(staged_objects.items())),
            content_bytes=tuple(sorted(staged_content.items())),
            signed_bytes=tuple(sorted(signed_bytes.items())),
            transitions=(*base.transitions, record),
            used_state_incarnations=(
                (
                    *base.used_state_incarnations,
                    candidate.allocate_state_incarnation,
                )
                if candidate.allocate_state_incarnation is not None
                else base.used_state_incarnations
            ),
            used_clock_incarnations=(
                (*base.used_clock_incarnations, next_clock)
                if next_clock != base.clock_incarnation
                else base.used_clock_incarnations
            ),
            used_signing_keys=(
                (*base.used_signing_keys, next_key)
                if next_key != base.authority_key_id
                else base.used_signing_keys
            ),
            retired_signing_keys=retired,
            clock_sample_high_watermarks=tuple(sorted(next_high_watermarks.items())),
        )
        _require(
            len(next_snapshot.used_clock_incarnations) <= MAX_AUTHORITY_INCARNATIONS
            and len(next_snapshot.used_signing_keys) <= MAX_AUTHORITY_INCARNATIONS
            and len(next_snapshot.used_state_incarnations)
            <= MAX_AUTHORITY_INCARNATIONS,
            "authority identity-history capacity exhausted; retire generation",
        )
        _validate_atomic_snapshot(next_snapshot)
        _require(
            self._snapshot is base,
            "atomic base pointer changed before final apply",
        )
        next_snapshot_root = self._coordinator.install_locked(
            self,
            expected_snapshot=base,
            expected_snapshot_root=self._snapshot_root,
            next_snapshot=next_snapshot,
        )
        self._snapshot = next_snapshot
        self._snapshot_root = next_snapshot_root
        self._trusted_clock_sample = (
            0 if next_clock != base.clock_incarnation else commit_time
        )
        cut("AFTER_POINTER_APPLY_BEFORE_ACK")
        return record


def _fixture_continuous_recovery_clock_sample(
    snapshot: ImmutableAuthoritySnapshot,
) -> int:
    """Return the synthetic source's explicit continuous recovery observation."""

    sample = _tuple_map(snapshot.clock_sample_high_watermarks).get(
        snapshot.clock_incarnation
    )
    _require(
        _safe_int(sample),
        "fixture recovery source lacks the current incarnation high-water mark",
    )
    return sample


def _preflight_snapshot_pairs(
    entries: Any,
    *,
    label: str,
    maximum_entries: int,
    maximum_value_bytes: int | None = None,
) -> None:
    """Bound one immutable tuple-map before allocating its lookup dictionary."""

    _require(type(entries) is tuple, f"{label} is not an exact tuple")
    _require(
        len(entries) <= maximum_entries,
        f"{label} exceeds its entry-count limit",
    )
    prior_key: str | None = None
    aggregate_bytes = 0
    for entry in entries:
        _require(
            type(entry) is tuple and len(entry) == 2,
            f"{label} contains a malformed entry",
        )
        key, value = entry
        _require(
            type(key) is str and _is_hex64(key),
            f"{label} contains a noncanonical digest key",
        )
        _require(
            prior_key is None or key > prior_key,
            f"{label} keys are duplicate or unordered",
        )
        prior_key = key
        if maximum_value_bytes is not None:
            _require(type(value) is bytes, f"{label} value is not exact bytes")
            aggregate_bytes += len(value)
            _require(
                aggregate_bytes <= maximum_value_bytes,
                f"{label} exceeds its aggregate byte limit",
            )


def _preflight_atomic_snapshot(snapshot: Any) -> None:
    """Reject recovery resource abuse before maps, hashes, or JSON allocation."""

    _require(
        type(snapshot) is ImmutableAuthoritySnapshot,
        "authority snapshot type is not exact",
    )
    for value, label in (
        (snapshot.store_id, "authority store ID"),
        (snapshot.authority_principal, "authority principal"),
        (snapshot.authority_key_id, "authority key ID"),
        (snapshot.clock_incarnation, "authority clock incarnation"),
    ):
        _require(
            _bounded_utf8_octets(
                value,
                maximum=MAX_CANONICAL_STRING_CHARS,
                label=label,
            )
            > 0,
            f"{label} is empty",
        )
    _require(
        _is_authority_digest(snapshot.security_state_digest)
        and (snapshot.state_digest is None or _is_hex64(snapshot.state_digest)),
        "authority snapshot security or state digest is noncanonical",
    )
    _require(
        _safe_int(snapshot.snapshot_version)
        and snapshot.snapshot_version <= MAX_AUTHORITY_TRANSITIONS,
        "authority snapshot version is outside its bound",
    )
    _preflight_snapshot_pairs(
        snapshot.objects,
        label="authority object index",
        maximum_entries=MAX_AUTHORITY_OBJECTS,
    )
    _preflight_snapshot_pairs(
        snapshot.content_bytes,
        label="authority content index",
        maximum_entries=MAX_AUTHORITY_OBJECTS,
        maximum_value_bytes=MAX_AUTHORITY_CONTENT_BYTES,
    )
    _preflight_snapshot_pairs(
        snapshot.signed_bytes,
        label="authority signed-byte index",
        maximum_entries=MAX_AUTHORITY_OBJECTS,
        maximum_value_bytes=MAX_AUTHORITY_SIGNED_BYTES,
    )
    _require(
        type(snapshot.transitions) is tuple
        and len(snapshot.transitions) <= MAX_AUTHORITY_TRANSITIONS,
        "authority transition history is outside its bound",
    )
    for transition in snapshot.transitions:
        _require(
            type(transition) is AtomicTransitionRecord,
            "authority transition record type is not exact",
        )
    for label, values in (
        ("state-incarnation history", snapshot.used_state_incarnations),
        ("clock-incarnation history", snapshot.used_clock_incarnations),
        ("signing-key history", snapshot.used_signing_keys),
        ("retired signing-key history", snapshot.retired_signing_keys),
    ):
        _require(
            type(values) is tuple and len(values) <= MAX_AUTHORITY_INCARNATIONS,
            f"{label} is outside its bound",
        )
        _require(
            all(
                type(item) is str
                and _bounded_utf8_octets(
                    item,
                    maximum=MAX_CANONICAL_STRING_CHARS,
                    label=label,
                )
                <= MAX_CANONICAL_STRING_CHARS
                for item in values
            ),
            f"{label} contains a noncanonical value",
        )
    high_watermarks = snapshot.clock_sample_high_watermarks
    _require(
        type(high_watermarks) is tuple
        and len(high_watermarks) <= MAX_AUTHORITY_INCARNATIONS,
        "clock high-watermark index is outside its bound",
    )
    prior_clock: str | None = None
    for entry in high_watermarks:
        _require(
            type(entry) is tuple
            and len(entry) == 2
            and type(entry[0]) is str
            and _bounded_utf8_octets(
                entry[0],
                maximum=MAX_CANONICAL_STRING_CHARS,
                label="clock high-watermark incarnation",
            )
            <= MAX_CANONICAL_STRING_CHARS
            and _safe_int(entry[1])
            and (prior_clock is None or entry[0] > prior_clock),
            "clock high-watermark entry is malformed, duplicate, or unordered",
        )
        prior_clock = entry[0]
    aggregate_values = tuple(value for _digest_key, value in snapshot.objects)
    validate_immutable(
        aggregate_values,
        limits=replace(
            _AUTHORITY_STORED_VALUE_LIMITS,
            max_depth=MAX_AUTHORITY_CANONICAL_DEPTH + 1,
            max_nodes=MAX_AUTHORITY_RECOVERY_NODES + 1,
            max_collection_items=MAX_AUTHORITY_OBJECTS,
        ),
        type_ids=_CANONICAL_ARTIFACT_TYPE_IDS,
        error_type=ProbeError,
    )
    for _digest_key, blob in snapshot.signed_bytes:
        envelope = _parse_signed_envelope(blob)
        _require(
            _canonical_json_bytes(envelope) == blob,
            "signed artifact bytes are not canonical",
        )


def _validate_atomic_snapshot(
    snapshot: ImmutableAuthoritySnapshot,
    *,
    preflight_complete: bool = False,
) -> None:
    if not preflight_complete:
        _preflight_atomic_snapshot(snapshot)
    objects = _tuple_map(snapshot.objects)
    content = _tuple_map(snapshot.content_bytes)
    signed = _tuple_map(snapshot.signed_bytes)
    _require(snapshot.snapshot_version == len(snapshot.transitions), "version drift")
    if snapshot.snapshot_version == 0:
        _require(
            snapshot.state is None
            and snapshot.state_digest is None
            and not objects
            and not content
            and not signed
            and not snapshot.transitions,
            "empty authority snapshot is malformed",
        )
        _require(
            snapshot.used_clock_incarnations == (snapshot.clock_incarnation,),
            "empty snapshot lacks its one allocated clock incarnation",
        )
        _require(
            snapshot.used_signing_keys == (snapshot.authority_key_id,),
            "empty snapshot lacks its one allocated signing key",
        )
        _require(
            snapshot.clock_sample_high_watermarks == ((snapshot.clock_incarnation, 0),),
            "empty snapshot has fabricated clock progress",
        )
        return
    _require(set(objects) == set(content), "object/content index mismatch")
    for item_digest, item in objects.items():
        _require(item_digest == _digest(item), "object key digest mismatch")
        _require(
            content[item_digest] == _canonical_bytes(item),
            "object canonical bytes mismatch",
        )
    state = snapshot.state
    _require(snapshot.state_digest == _digest(state), "state digest drift")
    _require(objects.get(snapshot.state_digest) == state, "state missing")
    _require(
        content.get(snapshot.state_digest) == _canonical_bytes(state),
        "state bytes missing",
    )
    _state_type_id, state_snapshot = _artifact_field_snapshot(state)
    current_state_incarnation = dict(state_snapshot).get("state_incarnation")
    if current_state_incarnation is not None:
        _require(
            snapshot.used_state_incarnations == (current_state_incarnation,),
            "state-incarnation ancestry mismatch",
        )
        allocations = tuple(
            item
            for item in objects.values()
            if isinstance(item, ParentSelectorAllocationReceipt)
        )
        _require(len(allocations) == 1, "recovery lacks one parent allocation")
        _validate_parent_allocation(
            allocations[0],
            store_id=snapshot.store_id,
            state_incarnation=current_state_incarnation,
        )
    prior: str | None = None
    operation_ids: set[str] = set()
    _require(snapshot.used_clock_incarnations, "clock ancestry is empty")
    _require(snapshot.used_signing_keys, "signing-key ancestry is empty")
    expected_clock = snapshot.used_clock_incarnations[0]
    expected_key = snapshot.used_signing_keys[0]
    expected_security_state = snapshot.transitions[0].security_state_digest
    used_clocks_in_order: list[str] = [expected_clock]
    high_watermarks: dict[str, int] = {}
    referenced_signed_digests: set[str] = set()
    for index, transition in enumerate(snapshot.transitions, start=1):
        _require(
            objects.get(_digest(transition)) == transition,
            "transition record is not content-addressed",
        )
        operation_commitment = objects.get(transition.operation_commitment_digest)
        _require(
            isinstance(
                operation_commitment,
                AuthorityTransitionOperationCommitment,
            ),
            "transition operation commitment is absent",
        )
        _require(transition.store_id == snapshot.store_id, "cross-store transition")
        _require(
            transition.authority_principal == snapshot.authority_principal,
            "cross-authority transition",
        )
        _require(transition.selector_version == index, "selector version gap")
        _require(
            transition.operation_id not in operation_ids,
            "operation identity was committed twice",
        )
        operation_ids.add(transition.operation_id)
        _require(
            transition.commit_clock_incarnation == expected_clock,
            "transition did not use the operation-chain current clock",
        )
        prior_sample = high_watermarks.get(transition.commit_clock_incarnation, 0)
        _require(
            transition.exact_commit_time >= prior_sample,
            "transition clock sample rolled back",
        )
        high_watermarks[transition.commit_clock_incarnation] = (
            transition.exact_commit_time
        )
        _require(
            transition.signing_key_id == expected_key
            and transition.security_state_digest == expected_security_state,
            "transition did not use the operation-chain current security state",
        )
        _require(
            transition.selector_digest in content,
            "installed selector bytes absent",
        )
        _require(transition.prior_state_digest == prior, "broken state ancestry")
        _require(
            transition.installed_state_digest in content,
            "installed state bytes absent",
        )
        generic_name, specialized_names = _receipt_schema(
            transition.store_id,
            transition.transition_kind,
        )
        expected_generic_type = _stable_artifact_type_id(generic_name)
        expected_specialized_types = tuple(
            _stable_artifact_type_id(item) for item in specialized_names
        )
        expected_co_types = tuple(
            _stable_artifact_type_id(item)
            for item in _co_committed_object_schema(
                transition.store_id,
                transition.transition_kind,
            )
        )
        _require(
            transition.specialized_receipt_types == expected_specialized_types
            and transition.required_specialized_receipt_types
            == expected_specialized_types,
            "receipt set differs from the closed transition schema",
        )
        _require(
            transition.co_committed_object_types == expected_co_types
            and transition.required_co_committed_object_types == expected_co_types,
            "co-committed object set differs from the closed transition schema",
        )
        _require(
            len(set(transition.specialized_receipt_digests))
            == len(transition.specialized_receipt_digests),
            "duplicate transition receipt",
        )
        for receipt_digest in (
            transition.generic_commit_digest,
            *transition.specialized_receipt_digests,
        ):
            referenced_signed_digests.add(receipt_digest)
            _require(receipt_digest in signed, "signed receipt bytes absent")
            payload = objects.get(receipt_digest)
            _require(payload is not None, "signed receipt payload absent")
            envelope = _parse_signed_envelope(signed[receipt_digest])
            _require(
                envelope["signing_key_id"] == transition.signing_key_id,
                "receipt signing key differs from transition-time key",
            )
            _require(
                envelope["security_state_digest"] == transition.security_state_digest,
                "receipt security differs from transition-time state",
            )
            _verify_signed_bytes(
                payload,
                signed[receipt_digest],
                expected_principal=snapshot.authority_principal,
                expected_key_id=transition.signing_key_id,
                expected_security_state=transition.security_state_digest,
            )
        _require(
            transition.generic_commit_digest in objects
            and transition.selector_digest in objects
            and all(item in objects for item in transition.specialized_receipt_digests)
            and all(item in objects for item in transition.co_committed_object_digests),
            "transition bundle payload is absent",
        )
        generic_payload = objects[transition.generic_commit_digest]
        selector_payload = objects[transition.selector_digest]
        specialized_payloads = tuple(
            objects[item] for item in transition.specialized_receipt_digests
        )
        co_committed_objects = tuple(
            objects[item] for item in transition.co_committed_object_digests
        )
        _require(
            _artifact_type_id(generic_payload) == expected_generic_type,
            "generic commit type differs from the closed transition schema",
        )
        _require(
            tuple(_artifact_type_id(item) for item in specialized_payloads)
            == expected_specialized_types,
            "specialized payload type differs from the closed transition schema",
        )
        _require(
            tuple(_artifact_type_id(item) for item in co_committed_objects)
            == expected_co_types,
            "co-committed payload type differs from the closed transition schema",
        )
        _require(
            len(set(transition.co_committed_object_digests))
            == len(transition.co_committed_object_digests),
            "duplicate co-committed object digest",
        )
        if transition.deadline_intent_set_digest is None:
            recovered_intents: tuple[
                AuthorizationDeadlineConditionIntent,
                ...,
            ] = ()
        else:
            recovered = objects.get(transition.deadline_intent_set_digest)
            _require(
                isinstance(recovered, AuthorizationDeadlineConditionIntentSet),
                "deadline intent set absent",
            )
            _require(
                recovered == _intent_set_artifact(recovered.intents),
                "deadline intent set is noncanonical",
            )
            recovered_intents = recovered.intents
        receipt_free_roots = operation_commitment.receipt_free_object_digests
        _require(
            receipt_free_roots == tuple(sorted(set(receipt_free_roots))),
            "operation commitment object roots are noncanonical",
        )
        for object_digest in receipt_free_roots:
            _require(
                object_digest in objects,
                "operation commitment references an absent receipt-free object",
            )
        expected_operation_commitment = AuthorityTransitionOperationCommitment(
            store_id=transition.store_id,
            authority_principal=transition.authority_principal,
            transition_kind=transition.transition_kind,
            operation_id=transition.operation_id,
            expected_prior_state_digest=transition.prior_state_digest,
            expected_prior_selector_version=index - 1,
            candidate_successor_digest=transition.installed_state_digest,
            receipt_free_object_digests=receipt_free_roots,
            deadline_intent_set_digest=(
                _intent_set_digest(recovered_intents) if recovered_intents else None
            ),
            generic_commit_type_id=expected_generic_type,
            specialized_receipt_type_ids=expected_specialized_types,
            co_committed_object_type_ids=expected_co_types,
            next_clock_incarnation=operation_commitment.next_clock_incarnation,
            next_security_state_digest=None,
            next_authority_key_id=None,
            allocated_state_incarnation=(
                current_state_incarnation if index == 1 else None
            ),
        )
        _require(
            operation_commitment == expected_operation_commitment
            and _digest(operation_commitment) == transition.operation_commitment_digest,
            "operation commitment does not reconstruct from recovered inputs",
        )
        if operation_commitment.next_clock_incarnation is not None:
            _require(
                transition.transition_kind == "OBSERVER_AUTHORIZATION_CLOCK_RESTART"
                and operation_commitment.next_clock_incarnation
                not in used_clocks_in_order,
                "clock restart commitment is not fresh or closed",
            )
            expected_clock = operation_commitment.next_clock_incarnation
            used_clocks_in_order.append(expected_clock)
        _generic_type_id, generic_snapshot = _artifact_field_snapshot(generic_payload)
        recovered_conditions = dict(generic_snapshot).get("deadline_conditions", ())
        recovery_context = AtomicReceiptContext(
            store_id=transition.store_id,
            authority_principal=transition.authority_principal,
            transition_kind=transition.transition_kind,
            operation_id=transition.operation_id,
            operation_commitment_digest=(transition.operation_commitment_digest),
            prior_state_digest=transition.prior_state_digest,
            installed_state_digest=transition.installed_state_digest,
            selector_version=transition.selector_version,
            commit_clock_incarnation=transition.commit_clock_incarnation,
            exact_commit_time=transition.exact_commit_time,
            signing_key_id=transition.signing_key_id,
            security_state_digest=transition.security_state_digest,
            deadline_intents=recovered_intents,
            deadline_conditions=recovered_conditions,
        )
        if recovered_intents:
            _validate_intent_evaluations(
                recovered_intents,
                recovered_conditions,
                installed_successor_digest=transition.installed_state_digest,
                installed_selector_version=transition.selector_version,
            )
            _require(
                transition.deadline_evaluation_set_digest
                == recovered_conditions[0].evaluation_set_digest,
                "transition deadline evaluation root mismatch",
            )
        else:
            _require(
                transition.deadline_evaluation_set_digest is None
                and recovered_conditions == (),
                "unexpected deadline evaluation",
            )
        recovered_bundle = AtomicReceiptBundle(
            generic_commit_payload=generic_payload,
            selector=selector_payload,
            specialized_payloads=specialized_payloads,
            co_committed_objects=co_committed_objects,
        )
        _validate_atomic_receipt_bundle(recovery_context, recovered_bundle)
        _validate_transition_semantics(
            prior_state=(
                None
                if transition.prior_state_digest is None
                else objects[transition.prior_state_digest]
            ),
            installed_state=objects[transition.installed_state_digest],
            staged_objects=objects,
            context=recovery_context,
            bundle=recovered_bundle,
        )
        prior = transition.installed_state_digest
    _require(
        set(signed) == referenced_signed_digests,
        "signed-byte store has missing or unreferenced artifacts",
    )
    _require(prior == snapshot.state_digest, "selected state is not history tip")
    _require(
        len(set(snapshot.used_clock_incarnations))
        == len(snapshot.used_clock_incarnations),
        "clock incarnation reused",
    )
    _require(
        len(set(snapshot.used_signing_keys)) == len(snapshot.used_signing_keys),
        "signing key reused",
    )
    _require(
        expected_clock == snapshot.clock_incarnation
        and tuple(used_clocks_in_order) == snapshot.used_clock_incarnations,
        "used clock-incarnation ancestry mismatch",
    )
    _require(
        snapshot.authority_key_id == expected_key
        and snapshot.security_state_digest == expected_security_state
        and snapshot.used_signing_keys == (expected_key,)
        and not snapshot.retired_signing_keys,
        "closed probe security state drifted without a rotation transition",
    )
    recorded_high_watermarks = _tuple_map(snapshot.clock_sample_high_watermarks)
    expected_high_watermarks = dict(high_watermarks)
    expected_high_watermarks.setdefault(snapshot.clock_incarnation, 0)
    _require(
        recorded_high_watermarks == expected_high_watermarks,
        "clock high-watermark mismatch",
    )


@dataclass(frozen=True)
class AuthorizationDeadlineConditionIntent:
    store_id: str
    authority_principal: str
    transition_kind: str
    operation_id: str
    expected_prior_state_digest: str | None
    expected_prior_selector_version: int
    security_state_digest: str
    purpose: str
    deadline_kind: str
    clock_incarnation: str
    exclusive_deadline: int
    qualified_effective_deadline_margin: int
    authorization_linearization_mode: str
    qualified_completion_bound: int
    timing_qualification_digest: str | None
    transaction_manager_guarantee: str


@dataclass(frozen=True)
class AuthorizationDeadlineConditionIntentSet:
    intents: tuple[AuthorizationDeadlineConditionIntent, ...]
    canonical_keys: tuple[tuple[str, str, str], ...]


def _intent_set_artifact(
    intents: Sequence[AuthorizationDeadlineConditionIntent],
) -> AuthorizationDeadlineConditionIntentSet:
    intent_tuple = tuple(intents)
    keys = tuple(
        (item.purpose, item.deadline_kind, item.operation_id) for item in intent_tuple
    )
    _require(keys == tuple(sorted(keys)), "deadline intent set is not canonical")
    _require(len(set(keys)) == len(keys), "duplicate deadline intent")
    return AuthorizationDeadlineConditionIntentSet(
        intents=intent_tuple,
        canonical_keys=keys,
    )


def _intent_set_digest(
    intents: Sequence[AuthorizationDeadlineConditionIntent],
) -> str:
    return _digest(_intent_set_artifact(intents))


def _intent(
    purpose: str,
    kind: str,
    clock: str,
    deadline: int,
    *,
    store_id: str,
    authority_principal: str,
    transition_kind: str,
    operation_id: str,
    expected_prior_state_digest: str | None,
    expected_prior_selector_version: int,
    security_state_digest: str,
    margin: int = 0,
    timing_qualification_digest: str | None = None,
) -> AuthorizationDeadlineConditionIntent:
    _require(kind in DEADLINE_KINDS, "unknown deadline intent kind")
    _require(
        purpose
        in {
            AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE,
            EXPIRY_AT_OR_AFTER_EXCLUSIVE_DEADLINE,
        },
        "unknown deadline intent purpose",
    )
    _require(_safe_int(deadline) and _safe_int(margin), "unsafe deadline intent")
    _require(
        margin == 0 and timing_qualification_digest is None,
        "this closed probe permits only in-lock transaction-manager linearization",
    )
    return AuthorizationDeadlineConditionIntent(
        store_id=store_id,
        authority_principal=authority_principal,
        transition_kind=transition_kind,
        operation_id=operation_id,
        expected_prior_state_digest=expected_prior_state_digest,
        expected_prior_selector_version=expected_prior_selector_version,
        security_state_digest=security_state_digest,
        purpose=purpose,
        deadline_kind=kind,
        clock_incarnation=clock,
        exclusive_deadline=deadline,
        qualified_effective_deadline_margin=margin,
        authorization_linearization_mode="TRANSACTION_MANAGER_LINEARIZATION",
        qualified_completion_bound=margin,
        timing_qualification_digest=timing_qualification_digest,
        transaction_manager_guarantee=("CLOCK_PREDICATE_AND_POINTER_APPLY_ONE_LOCK"),
    )


def _evaluate_intents(
    intents: Sequence[AuthorizationDeadlineConditionIntent],
    *,
    commit_time: int,
    installed_successor_digest: str,
    installed_selector_version: int,
) -> tuple[CommitTimeDeadlineCondition, ...]:
    _require(bool(intents), "deadline evaluation set is empty")
    keys = [(item.purpose, item.deadline_kind) for item in intents]
    _require(len(set(keys)) == len(keys), "duplicate deadline intent")
    timing_profiles = {
        (
            item.authorization_linearization_mode,
            item.qualified_completion_bound,
            item.timing_qualification_digest,
        )
        for item in intents
    }
    _require(
        len(timing_profiles) == 1,
        "one deadline transaction cannot mix timing profiles",
    )
    intent_set_digest = _intent_set_digest(intents)
    evaluation_set_digest = _semantic_digest(
        "ncp.b01.CommitTimeDeadlineConditionSet@1",
        (
            intent_set_digest,
            commit_time,
            len(intents),
            installed_successor_digest,
            installed_selector_version,
        ),
    )
    return tuple(
        _deadline_condition(
            intent=item,
            commit_time=commit_time,
            evaluation_set_digest=evaluation_set_digest,
            evaluation_index=index,
            evaluation_count=len(intents),
            installed_successor_digest=installed_successor_digest,
            installed_selector_version=installed_selector_version,
        )
        for index, item in enumerate(intents)
    )


def _validate_intent_evaluations(
    intents: Sequence[AuthorizationDeadlineConditionIntent],
    evaluations: Sequence[CommitTimeDeadlineCondition],
    *,
    installed_successor_digest: str,
    installed_selector_version: int,
) -> None:
    _require(len(intents) == len(evaluations), "missing deadline evaluation")
    samples = {item.trusted_commit_time_sample for item in evaluations}
    _require(len(samples) == 1, "deadline set uses more than one commit sample")
    sample = next(iter(samples))
    expected_set = _semantic_digest(
        "ncp.b01.CommitTimeDeadlineConditionSet@1",
        (
            _intent_set_digest(intents),
            sample,
            len(intents),
            installed_successor_digest,
            installed_selector_version,
        ),
    )
    for index, (intent, evaluation) in enumerate(
        zip(intents, evaluations, strict=True)
    ):
        _require(
            intent.transaction_manager_guarantee
            == evaluation.transaction_manager_guarantee,
            "deadline guarantee substitution",
        )
        _require(
            intent.qualified_effective_deadline_margin
            == evaluation.qualified_effective_deadline_margin,
            "deadline margin substitution",
        )
        _validate_condition(
            evaluation,
            intent=intent,
            evaluation_set_digest=expected_set,
            evaluation_index=index,
            evaluation_count=len(intents),
            installed_successor_digest=installed_successor_digest,
            installed_selector_version=installed_selector_version,
        )


def _closed_identifier(value: Any, *, label: str) -> str:
    _require(
        type(value) is str and 0 < len(value) <= 256,
        f"{label} must be an exact bounded nonempty string",
    )
    _require(
        value not in {"*", "default", "unknown"}
        and all(ord(character) >= 0x20 and character != "\x7f" for character in value),
        f"{label} contains a wildcard, default, unknown, or control value",
    )
    return value


ObserverManifestReadScope = CanonicalObserverReadScope


def _observer_manifest_read_scope_digest(scope: ObserverManifestReadScope) -> str:
    return canonical_scope_digest(scope)


@dataclass(frozen=True)
class ObserverDefaultDenyManifestEntry:
    authority_realm_key: tuple[str, str]
    authenticated_principal: str
    endpoint_profile: str
    audience: str
    logical_session: str
    session_generation: str
    operations: tuple[str, ...]
    read_scopes: tuple[ObserverManifestReadScope, ...]
    security_state_digest: str
    security_epoch: int
    revocation_epoch: int


@dataclass(frozen=True)
class ObserverDefaultDenyManifest:
    manifest_id: str
    manifest_version: int
    issuer_principal: str
    issuer_key_id: str
    capability_issuer_principal: str
    capability_issuer_key_id: str
    capability_issuer_incarnation: str
    authority_realm_key: tuple[str, str]
    default_decision: str
    wildcard_entries_allowed: bool
    entries: tuple[ObserverDefaultDenyManifestEntry, ...]


def _manifest_scope_digests(
    entry: ObserverDefaultDenyManifestEntry,
) -> tuple[str, ...]:
    return tuple(scope.scope_digest for scope in entry.read_scopes)


@dataclass(frozen=True)
class VerifiedObserverTransportPrincipal:
    authority_realm_key: tuple[str, str]
    authenticated_principal: str
    connection_instance: str
    replay_domain: str
    endpoint_profile: str
    audience: str
    logical_session: str
    session_generation: str
    default_deny_manifest_digest: str
    security_state_digest: str
    security_epoch: int
    revocation_epoch: int
    coordinator_clock_incarnation: str
    verified_at: int
    not_after: int
    transport_verification_evidence_digest: str


@dataclass(frozen=True)
class ObserverDescriptor:
    responder_principal: str
    authority_realm_key: tuple[str, str]
    descriptor_revision: int
    logical_session: str
    session_generation: str
    security_state_digest: str
    security_epoch: int
    revocation_epoch: int
    privacy_policy_digest: str
    declared_stream_digest: str
    allowed_boundary_member_identities: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class ObserverReadCapability:
    capability_id: str
    interface_kind: str
    issuer_principal: str
    issuer_key_id: str
    issuer_incarnation: str
    authority_realm_key: tuple[str, str]
    observer_principal: str
    verified_transport_context_digest: str
    transport_connection_instance: str
    transport_replay_domain: str
    default_deny_manifest_digest: str
    manifest_entry_digest: str
    manifest_session_scope: tuple[str, str]
    operations: tuple[str, ...]
    exact_scope_digests: tuple[str, ...]
    security_state_digest: str
    security_epoch: int
    revocation_epoch: int
    coordinator_clock_incarnation: str
    issued_at: int
    not_after: int


@dataclass(frozen=True)
class ObserverReadCapabilitySeal:
    issuer_principal: str
    issuer_key_id: str
    issuer_incarnation: str
    issuance_sequence: int
    capability_digest: str
    verified_transport_context_digest: str
    default_deny_manifest_digest: str
    manifest_entry_digest: str
    installed_registry_root: str
    authentication_tag: str


@dataclass(frozen=True)
class ObserverReadCapabilityIssuerSnapshot:
    issuer_principal: str
    issuer_key_id: str
    issuer_incarnation: str
    snapshot_version: int
    security_state_digest: str
    security_epoch: int
    revocation_epoch: int
    default_deny_manifest_digest: str
    retained_issuances: tuple[tuple[str, str, str, str], ...]


@dataclass(frozen=True)
class ObserverReadCapabilityEvidence:
    verified_transport_context: VerifiedObserverTransportPrincipal
    capability: ObserverReadCapability
    seal: ObserverReadCapabilitySeal
    issuer_snapshot: ObserverReadCapabilityIssuerSnapshot


def _validate_default_deny_manifest(manifest: ObserverDefaultDenyManifest) -> None:
    _require(
        type(manifest) is ObserverDefaultDenyManifest,
        "default-deny manifest type is not exact",
    )
    _assert_deeply_immutable(manifest)
    _closed_identifier(manifest.manifest_id, label="manifest ID")
    _closed_identifier(manifest.issuer_principal, label="manifest issuer principal")
    _closed_identifier(manifest.issuer_key_id, label="manifest issuer key")
    _closed_identifier(
        manifest.capability_issuer_principal,
        label="manifest capability issuer principal",
    )
    _closed_identifier(
        manifest.capability_issuer_key_id,
        label="manifest capability issuer key",
    )
    _closed_identifier(
        manifest.capability_issuer_incarnation,
        label="manifest capability issuer incarnation",
    )
    _require(
        manifest.manifest_version == 1
        and manifest.default_decision == "DENY"
        and manifest.wildcard_entries_allowed is False,
        "observer manifest is not exact default-deny version 1",
    )
    _require(
        type(manifest.authority_realm_key) is tuple
        and len(manifest.authority_realm_key) == 2,
        "manifest authority realm key is malformed",
    )
    for member in manifest.authority_realm_key:
        _closed_identifier(member, label="authority realm member")
    _require(
        manifest.issuer_principal == manifest.authority_realm_key[0],
        "manifest issuer is not the authority-realm server principal",
    )
    _require(
        (
            manifest.capability_issuer_principal,
            manifest.capability_issuer_key_id,
            manifest.capability_issuer_incarnation,
        )
        == (
            CAPABILITY_ISSUER_PRINCIPAL,
            CAPABILITY_ISSUER_KEY_ID,
            CAPABILITY_ISSUER_INCARNATION,
        )
        and _is_uuid4(manifest.capability_issuer_incarnation),
        "manifest does not select the exact installed capability issuer",
    )
    _require(
        type(manifest.entries) is tuple and 0 < len(manifest.entries) <= MAX_GRANTS,
        "manifest entry count is outside its bound",
    )
    entry_keys: list[tuple[str, str, str, str]] = []
    for entry in manifest.entries:
        _require(
            type(entry) is ObserverDefaultDenyManifestEntry,
            "manifest entry type is not exact",
        )
        for value, label in (
            (entry.authenticated_principal, "manifest principal"),
            (entry.endpoint_profile, "manifest endpoint profile"),
            (entry.audience, "manifest audience"),
            (entry.logical_session, "manifest logical session"),
            (entry.session_generation, "manifest session generation"),
        ):
            _closed_identifier(value, label=label)
        _require(
            entry.authority_realm_key == manifest.authority_realm_key
            and entry.endpoint_profile == "production-secure",
            "manifest entry uses a cross-realm or unsupported endpoint profile",
        )
        _require(
            _is_uuid4(entry.session_generation),
            "manifest session generation is not a canonical lowercase UUIDv4",
        )
        _require(
            type(entry.operations) is tuple
            and entry.operations == OBSERVER_READ_OPERATIONS
            and all(type(operation) is str for operation in entry.operations)
            and not (set(entry.operations) & OBSERVER_WRITE_OR_AUTHORITY_OPERATIONS),
            "manifest entry is not the exact closed read-only operation set",
        )
        _require(
            type(entry.read_scopes) is tuple
            and bool(entry.read_scopes)
            and len(entry.read_scopes) <= MAX_ITEMS,
            "manifest literal read-scope set is empty or outside its bound",
        )
        for scope in entry.read_scopes:
            _require(
                type(scope) is ObserverManifestReadScope,
                "manifest read-scope type is not exact",
            )
            try:
                validate_scope(scope)
            except BridgeValidationError as exc:
                raise ProbeError("manifest read scope is not canonical") from exc
            _require(
                scope.operation in entry.operations
                and scope.operation not in OBSERVER_WRITE_OR_AUTHORITY_OPERATIONS
                and scope.route_class in READ_ROUTE_CLASS_SHAPES
                and scope.scope_digest == _observer_manifest_read_scope_digest(scope)
                and scope.authority_realm_key == entry.authority_realm_key
                and scope.source_session_kind == "NCP_SESSION"
                and scope.logical_session_id == entry.logical_session
                and scope.source_generation == entry.session_generation
                and scope.authorization_audience == entry.audience,
                "manifest read scope is writable, unknown, or digest-mismatched",
            )
            _require(
                scope.literal_route
                == canonical_read_route(
                    realm=manifest.authority_realm_key[1],
                    logical_session_id=entry.logical_session,
                    route_class=scope.route_class,
                    channel=scope.channel,
                ),
                "manifest read scope uses a cross-realm, cross-session, or "
                "nonliteral route",
            )
        scope_digests = _manifest_scope_digests(entry)
        _require(
            scope_digests == tuple(sorted(set(scope_digests)))
            and all(_is_hex64(item) for item in scope_digests),
            "manifest literal read-scope set is noncanonical or duplicate",
        )
        _require(
            _is_authority_digest(entry.security_state_digest)
            and _safe_int(entry.security_epoch)
            and entry.security_epoch > 0
            and _safe_int(entry.revocation_epoch)
            and entry.revocation_epoch > 0,
            "manifest security coordinates are malformed or default",
        )
        entry_keys.append(
            (
                entry.authenticated_principal,
                entry.logical_session,
                entry.session_generation,
                entry.audience,
            )
        )
    _require(
        entry_keys == sorted(entry_keys) and len(entry_keys) == len(set(entry_keys)),
        "manifest entries are noncanonical or ambiguous",
    )


def _manifest_entry_for_context(
    manifest: ObserverDefaultDenyManifest,
    context: VerifiedObserverTransportPrincipal,
) -> ObserverDefaultDenyManifestEntry:
    _validate_default_deny_manifest(manifest)
    _require(
        type(context) is VerifiedObserverTransportPrincipal,
        "verified transport context type is not exact",
    )
    _assert_deeply_immutable(context)
    matches = tuple(
        entry
        for entry in manifest.entries
        if (
            entry.authority_realm_key,
            entry.authenticated_principal,
            entry.endpoint_profile,
            entry.audience,
            entry.logical_session,
            entry.session_generation,
            entry.security_state_digest,
            entry.security_epoch,
            entry.revocation_epoch,
        )
        == (
            context.authority_realm_key,
            context.authenticated_principal,
            context.endpoint_profile,
            context.audience,
            context.logical_session,
            context.session_generation,
            context.security_state_digest,
            context.security_epoch,
            context.revocation_epoch,
        )
    )
    _require(len(matches) == 1, "default-deny manifest has no unique exact grant")
    return matches[0]


def _validate_verified_transport_context(
    context: VerifiedObserverTransportPrincipal,
    *,
    manifest: ObserverDefaultDenyManifest,
    trusted_time: int,
) -> ObserverDefaultDenyManifestEntry:
    _require(
        type(context) is VerifiedObserverTransportPrincipal,
        "verified transport context type is not exact",
    )
    for value, label in (
        (context.authenticated_principal, "authenticated transport principal"),
        (context.connection_instance, "transport connection instance"),
        (context.replay_domain, "transport replay domain"),
        (context.endpoint_profile, "transport endpoint profile"),
        (context.audience, "transport audience"),
        (context.logical_session, "transport logical session"),
        (context.session_generation, "transport session generation"),
        (context.coordinator_clock_incarnation, "transport clock incarnation"),
    ):
        _closed_identifier(value, label=label)
    _require(
        context.default_deny_manifest_digest == _digest(manifest)
        and context.authority_realm_key == manifest.authority_realm_key,
        "verified transport context is cross-manifest or cross-realm",
    )
    _require(
        _is_authority_digest(context.security_state_digest)
        and _is_authority_digest(context.transport_verification_evidence_digest)
        and _safe_int(context.security_epoch)
        and context.security_epoch > 0
        and _safe_int(context.revocation_epoch)
        and context.revocation_epoch > 0
        and _safe_int(context.verified_at)
        and _safe_int(context.not_after)
        and _safe_int(trusted_time)
        and context.verified_at <= trusted_time < context.not_after,
        "verified transport context is malformed, future, stale, or expired",
    )
    return _manifest_entry_for_context(manifest, context)


def _capability_registry_root(
    *,
    capability: ObserverReadCapability,
    context: VerifiedObserverTransportPrincipal,
    manifest_entry: ObserverDefaultDenyManifestEntry,
    issuance_sequence: int,
) -> str:
    return _semantic_digest(
        "ncp.b01.ObserverReadCapabilityIssuerRegistry@1",
        (
            capability.capability_id,
            _digest(capability),
            _digest(context),
            _digest(manifest_entry),
            issuance_sequence,
        ),
    )


def _capability_seal_tag(seal_without_tag: tuple[Any, ...]) -> str:
    return hmac.new(
        _CAPABILITY_ISSUER_SEAL_KEY,
        b"NCP-B01-OBSERVER-READ-CAPABILITY-SEAL-V1\x00"
        + _canonical_bytes(seal_without_tag),
        hashlib.sha256,
    ).hexdigest()


class ObserverReadCapabilityIssuer:
    """Synthetic trusted issuer; the seal key is not part of caller evidence."""

    def issue(
        self,
        *,
        manifest: ObserverDefaultDenyManifest,
        context: VerifiedObserverTransportPrincipal,
        trusted_time: int,
    ) -> ObserverReadCapabilityEvidence:
        entry = _validate_verified_transport_context(
            context,
            manifest=manifest,
            trusted_time=trusted_time,
        )
        capability = ObserverReadCapability(
            capability_id=_uuid_for(
                (
                    "observer-read-capability",
                    _digest(context),
                    _digest(entry),
                    1,
                )
            ),
            interface_kind="SEALED_OBSERVER_READ_ONLY_FACADE",
            issuer_principal=CAPABILITY_ISSUER_PRINCIPAL,
            issuer_key_id=CAPABILITY_ISSUER_KEY_ID,
            issuer_incarnation=CAPABILITY_ISSUER_INCARNATION,
            authority_realm_key=context.authority_realm_key,
            observer_principal=context.authenticated_principal,
            verified_transport_context_digest=_digest(context),
            transport_connection_instance=context.connection_instance,
            transport_replay_domain=context.replay_domain,
            default_deny_manifest_digest=_digest(manifest),
            manifest_entry_digest=_digest(entry),
            manifest_session_scope=(
                context.logical_session,
                context.session_generation,
            ),
            operations=entry.operations,
            exact_scope_digests=_manifest_scope_digests(entry),
            security_state_digest=context.security_state_digest,
            security_epoch=context.security_epoch,
            revocation_epoch=context.revocation_epoch,
            coordinator_clock_incarnation=context.coordinator_clock_incarnation,
            issued_at=trusted_time,
            not_after=context.not_after,
        )
        registry_root = _capability_registry_root(
            capability=capability,
            context=context,
            manifest_entry=entry,
            issuance_sequence=1,
        )
        seal_fields = (
            CAPABILITY_ISSUER_PRINCIPAL,
            CAPABILITY_ISSUER_KEY_ID,
            CAPABILITY_ISSUER_INCARNATION,
            1,
            _digest(capability),
            _digest(context),
            _digest(manifest),
            _digest(entry),
            registry_root,
        )
        seal = ObserverReadCapabilitySeal(
            issuer_principal=CAPABILITY_ISSUER_PRINCIPAL,
            issuer_key_id=CAPABILITY_ISSUER_KEY_ID,
            issuer_incarnation=CAPABILITY_ISSUER_INCARNATION,
            issuance_sequence=1,
            capability_digest=_digest(capability),
            verified_transport_context_digest=_digest(context),
            default_deny_manifest_digest=_digest(manifest),
            manifest_entry_digest=_digest(entry),
            installed_registry_root=registry_root,
            authentication_tag=_capability_seal_tag(seal_fields),
        )
        snapshot = ObserverReadCapabilityIssuerSnapshot(
            issuer_principal=CAPABILITY_ISSUER_PRINCIPAL,
            issuer_key_id=CAPABILITY_ISSUER_KEY_ID,
            issuer_incarnation=CAPABILITY_ISSUER_INCARNATION,
            snapshot_version=1,
            security_state_digest=context.security_state_digest,
            security_epoch=context.security_epoch,
            revocation_epoch=context.revocation_epoch,
            default_deny_manifest_digest=_digest(manifest),
            retained_issuances=(
                (
                    capability.capability_id,
                    _digest(capability),
                    _digest(context),
                    _digest(seal),
                ),
            ),
        )
        return ObserverReadCapabilityEvidence(
            verified_transport_context=context,
            capability=capability,
            seal=seal,
            issuer_snapshot=snapshot,
        )


def _validate_capability_evidence(
    evidence: ObserverReadCapabilityEvidence,
    *,
    manifest: ObserverDefaultDenyManifest,
    trusted_time: int,
) -> ObserverDefaultDenyManifestEntry:
    _require(
        type(evidence) is ObserverReadCapabilityEvidence
        and type(evidence.verified_transport_context)
        is VerifiedObserverTransportPrincipal
        and type(evidence.capability) is ObserverReadCapability
        and type(evidence.seal) is ObserverReadCapabilitySeal
        and type(evidence.issuer_snapshot) is ObserverReadCapabilityIssuerSnapshot,
        "capability evidence contains an unregistered or subclassed shell",
    )
    _assert_deeply_immutable(evidence)
    context = evidence.verified_transport_context
    capability = evidence.capability
    seal = evidence.seal
    snapshot = evidence.issuer_snapshot
    entry = _validate_verified_transport_context(
        context,
        manifest=manifest,
        trusted_time=trusted_time,
    )
    _require(
        (
            capability.interface_kind,
            capability.issuer_principal,
            capability.issuer_key_id,
            capability.issuer_incarnation,
            capability.authority_realm_key,
            capability.observer_principal,
            capability.verified_transport_context_digest,
            capability.transport_connection_instance,
            capability.transport_replay_domain,
            capability.default_deny_manifest_digest,
            capability.manifest_entry_digest,
            capability.manifest_session_scope,
            capability.operations,
            capability.exact_scope_digests,
            capability.security_state_digest,
            capability.security_epoch,
            capability.revocation_epoch,
            capability.coordinator_clock_incarnation,
        )
        == (
            "SEALED_OBSERVER_READ_ONLY_FACADE",
            manifest.capability_issuer_principal,
            manifest.capability_issuer_key_id,
            manifest.capability_issuer_incarnation,
            context.authority_realm_key,
            context.authenticated_principal,
            _digest(context),
            context.connection_instance,
            context.replay_domain,
            _digest(manifest),
            _digest(entry),
            (context.logical_session, context.session_generation),
            OBSERVER_READ_OPERATIONS,
            _manifest_scope_digests(entry),
            context.security_state_digest,
            context.security_epoch,
            context.revocation_epoch,
            context.coordinator_clock_incarnation,
        )
        and not (set(capability.operations) & OBSERVER_WRITE_OR_AUTHORITY_OPERATIONS),
        "capability is not the exact sealed principal/manifest/session read facade",
    )
    _closed_identifier(capability.capability_id, label="capability ID")
    _require(
        _is_uuid4(capability.capability_id)
        and _safe_int(capability.issued_at)
        and _safe_int(capability.not_after)
        and capability.issued_at <= trusted_time < capability.not_after
        and capability.issued_at >= context.verified_at
        and capability.not_after <= context.not_after,
        "capability issuance window is malformed, future, stale, or widened",
    )
    expected_root = _capability_registry_root(
        capability=capability,
        context=context,
        manifest_entry=entry,
        issuance_sequence=seal.issuance_sequence,
    )
    seal_fields = (
        seal.issuer_principal,
        seal.issuer_key_id,
        seal.issuer_incarnation,
        seal.issuance_sequence,
        seal.capability_digest,
        seal.verified_transport_context_digest,
        seal.default_deny_manifest_digest,
        seal.manifest_entry_digest,
        seal.installed_registry_root,
    )
    _require(
        (
            seal.issuer_principal,
            seal.issuer_key_id,
            seal.issuer_incarnation,
            seal.issuance_sequence,
            seal.capability_digest,
            seal.verified_transport_context_digest,
            seal.default_deny_manifest_digest,
            seal.manifest_entry_digest,
            seal.installed_registry_root,
        )
        == (
            manifest.capability_issuer_principal,
            manifest.capability_issuer_key_id,
            manifest.capability_issuer_incarnation,
            1,
            _digest(capability),
            _digest(context),
            _digest(manifest),
            _digest(entry),
            expected_root,
        ),
        "capability issuer seal fields are forged, copied across context, or stale",
    )
    expected_tag = _capability_seal_tag(seal_fields)
    _require(
        _is_hex64(seal.authentication_tag)
        and hmac.compare_digest(seal.authentication_tag, expected_tag),
        "capability issuer authentication tag is invalid",
    )
    _require(
        (
            snapshot.issuer_principal,
            snapshot.issuer_key_id,
            snapshot.issuer_incarnation,
            snapshot.snapshot_version,
            snapshot.security_state_digest,
            snapshot.security_epoch,
            snapshot.revocation_epoch,
            snapshot.default_deny_manifest_digest,
            snapshot.retained_issuances,
        )
        == (
            manifest.capability_issuer_principal,
            manifest.capability_issuer_key_id,
            manifest.capability_issuer_incarnation,
            1,
            context.security_state_digest,
            context.security_epoch,
            context.revocation_epoch,
            _digest(manifest),
            (
                (
                    capability.capability_id,
                    _digest(capability),
                    _digest(context),
                    _digest(seal),
                ),
            ),
        ),
        "capability is absent from the exact retained issuer snapshot",
    )
    return entry


@dataclass(frozen=True)
class ObserverAttached:
    descriptor_digest: str
    canonical_grant_digest: str
    boundary_installation_set_receipt_digest: str
    observer_read_capability_digest: str
    installed_selector_version: int
    installed_selector_digest: str
    outer_commit_receipt_digest: str


@dataclass(frozen=True)
class ObserverGrantLedgerHead:
    registry_key: ObserverGrantRegistryKey
    full_boundary_key: TrustedDeliveryBoundaryGrantKey
    state_version: int
    prior_keyed_head_digest: str | None
    phase: str
    canonical_grant_digest: str
    boundary_installation_plan_digest: str
    activation_commitment_digest: str | None
    renewal_transition_fact_digest: str | None
    terminal_transition_fact_digest: str | None
    next_issuance_sequence: int
    consumed_predecessor_head_digests: tuple[str, ...]
    consumed_predecessor_fence_digests: tuple[str, ...]
    effective_server_installation_close: int
    effective_server_not_after: int
    coordinator_clock_incarnation: str
    clock_restart_ancestry: tuple[str, ...]
    distributed_authorization_closure_pending: bool
    deadline_intent_set_digest: str | None


SERVER_LEDGER_PHASES = frozenset({"PENDING_BOUNDARY_INSTALLATION", "LIVE", "TERMINAL"})


@dataclass(frozen=True)
class ObserverGrantRegistryHead:
    logical_session: str
    session_generation: str
    registry_incarnation: str
    state_version: int
    prior_registry_head_digest: str | None
    entries: tuple[tuple[str, str], ...]
    retained_lineage_tombstones: tuple[str, ...]


@dataclass(frozen=True)
class ObserverAuthorizationStateHead:
    server_principal: str
    authority_realm_key: tuple[str, str]
    logical_session: str
    session_generation: str
    state_incarnation: str
    state_version: int
    prior_authorization_head_digest: str | None
    descriptor_revision: int
    descriptor_digest: str
    privacy_policy_digest: str
    security_state_digest: str
    security_epoch: int
    revocation_epoch: int
    default_deny_manifest_digest: str
    coordinator_clock_policy_id: str
    coordinator_clock_incarnation: str
    observer_grant_registry_head_digest: str
    transition_fact_digest: str | None


@dataclass(frozen=True)
class InstalledObserverAuthorizationStateSelector:
    state_incarnation: str
    selector_version: int
    selected_head_digest: str
    generic_commit_receipt_digest: str


@dataclass(frozen=True)
class ObserverAuthorizationStateCommitReceipt:
    transition_kind: str
    operation_id: str
    operation_commitment_digest: str
    prior_outer_head_digest: str | None
    installed_outer_head_digest: str
    installed_selector_version: int
    deadline_intent_set_digest: str | None
    deadline_conditions: tuple[CommitTimeDeadlineCondition, ...]


@dataclass(frozen=True)
class ObserverGrantRegistryCommitReceipt:
    transition_kind: str
    operation_id: str
    operation_commitment_digest: str
    prior_outer_head_digest: str | None
    installed_outer_head_digest: str
    outer_commit_receipt_digest: str
    prior_registry_head_digest: str | None
    installed_registry_head_digest: str
    prior_entry_head_digest: str | None
    installed_entry_head_digest: str | None
    installed_selector_version: int
    installed_selector_digest: str
    sibling_preservation_digest: str


@dataclass(frozen=True)
class ObserverGrantBoundaryInstallationCommitment:
    operation_id: str
    deadline_intent_set_digest: str
    boundary_installation_plan_digest: str
    canonical_grant_digest: str
    pending_outer_head_digest: str
    pending_registry_head_digest: str
    pending_keyed_head_digest: str
    canonical_prepared_member_receipts: tuple[
        tuple[tuple[str, ...], str],
        ...,
    ]
    transition_kind: str
    predecessor_closure_receipt_digest: str | None


@dataclass(frozen=True)
class ObserverGrantBoundaryInstallationSetReceipt:
    commitment_digest: str
    canonical_prepared_member_receipts: tuple[
        tuple[tuple[str, ...], str],
        ...,
    ]
    prior_outer_head_digest: str
    installed_outer_head_digest: str
    prior_registry_head_digest: str
    installed_registry_head_digest: str
    prior_keyed_head_digest: str
    installed_keyed_head_digest: str
    installed_selector_version: int
    installed_selector_digest: str
    outer_commit_receipt_digest: str
    registry_commit_receipt_digest: str
    deadline_intent_set_digest: str
    deadline_conditions: tuple[CommitTimeDeadlineCondition, ...]


@dataclass(frozen=True)
class ObserverGrantRegistryActivationEntryProof:
    stable_registry_key: ObserverGrantRegistryKey
    full_boundary_key: TrustedDeliveryBoundaryGrantKey
    installed_outer_head_digest: str
    installed_registry_head_digest: str
    installed_keyed_head_digest: str
    boundary_installation_set_receipt_digest: str
    membership_path_digest: str
    installed_selector_version: int
    installed_selector_digest: str
    outer_commit_receipt_digest: str


@dataclass(frozen=True)
class ObserverGrantRenewalPredecessorFenceReceipt:
    stable_registry_key: ObserverGrantRegistryKey
    g0_full_boundary_key: TrustedDeliveryBoundaryGrantKey
    g1_full_boundary_key: TrustedDeliveryBoundaryGrantKey
    consumed_g0_keyed_head_digest: str
    installed_g1_pending_keyed_head_digest: str
    prior_registry_head_digest: str
    installed_registry_head_digest: str
    prior_outer_head_digest: str
    installed_outer_head_digest: str
    installed_selector_version: int
    installed_selector_digest: str
    outer_commit_receipt_digest: str
    registry_commit_receipt_digest: str
    g0_installation_commitment_digest: str
    g0_installation_set_receipt_digest: str
    g0_registry_activation_entry_proof_digest: str
    deadline_intent_digest: str
    deadline_condition: CommitTimeDeadlineCondition


@dataclass(frozen=True)
class ObserverGrantRenewalTransitionFact:
    operation_id: str
    stable_registry_key: ObserverGrantRegistryKey
    prior_outer_head_digest: str
    prior_registry_head_digest: str
    prior_g0_keyed_head_digest: str
    candidate_plan_digest: str
    candidate_grant_digest: str
    candidate_full_boundary_key: TrustedDeliveryBoundaryGrantKey
    expected_prior_selector_version: int
    deadline_intent_set_digest: str


@dataclass(frozen=True)
class ObserverGrantBoundaryInstallationFailureMemberEvidence:
    boundary_member_identity: tuple[str, ...]
    subreason: str
    evidence_digest: str


@dataclass(frozen=True)
class ObserverGrantTerminalTransitionFact:
    stable_registry_key: ObserverGrantRegistryKey
    prior_outer_head_digest: str
    prior_registry_head_digest: str
    prior_keyed_head_digest: str
    full_boundary_key: TrustedDeliveryBoundaryGrantKey
    complete_boundary_member_identities: tuple[tuple[str, ...], ...]
    terminal_reason: str
    actor_or_event: str
    authority_clock_incarnation: str
    reattachment_policy_rule_digest: str
    reattachment_policy_inputs_digest: str
    boundary_failure_evidence: tuple[
        ObserverGrantBoundaryInstallationFailureMemberEvidence, ...
    ]
    deadline_intent_digest: str | None


@dataclass(frozen=True)
class ObserverGrantTerminalTransitionReceipt:
    transition_fact_digest: str
    prior_outer_head_digest: str
    installed_outer_head_digest: str
    prior_registry_head_digest: str
    installed_registry_head_digest: str
    prior_keyed_head_digest: str
    installed_keyed_head_digest: str
    installed_selector_version: int
    installed_selector_digest: str
    outer_commit_receipt_digest: str
    registry_commit_receipt_digest: str
    deadline_conditions: tuple[CommitTimeDeadlineCondition, ...]


@dataclass(frozen=True)
class ObserverGrantReattachmentPolicyResult:
    installed_terminal_keyed_head_digest: str
    terminal_transition_receipt_digest: str
    policy_rule_digest: str
    requester_lineage_digest: str
    terminal_reason: str
    descriptor_security_scope_digest: str
    policy_inputs_digest: str
    deterministic_evaluator_digest: str
    authority_source_receipt_digest: str
    outcome: str
    unique_result_key: str
    installed_selector_version: int
    installed_selector_digest: str
    outer_commit_receipt_digest: str


@dataclass(frozen=True)
class ObserverAuthorizationClockRestartTransitionFact:
    prior_outer_head_digest: str
    prior_clock_incarnation: str
    new_clock_incarnation: str
    authenticated_restart_mapping: AuthenticatedClockMapping
    affected_registry_keys: tuple[str, ...]
    mapped_deadline_pairs: tuple[tuple[str, int, int, int, int], ...]
    complete_restart_ancestry_digest: str


@dataclass(frozen=True)
class ObserverAuthorizationClockRestartCommitReceipt:
    transition_fact_digest: str
    prior_outer_head_digest: str
    installed_outer_head_digest: str
    prior_registry_head_digest: str
    installed_registry_head_digest: str
    installed_selector_version: int
    installed_selector_digest: str
    outer_commit_receipt_digest: str
    registry_commit_receipt_digest: str
    affected_installed_keyed_head_digests: tuple[str, ...]


SERVER_TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "ATTACH_NEW_GRANT_LINEAGE": (
        frozenset({"ABSENT"}),
        "PENDING_BOUNDARY_INSTALLATION",
    ),
    "BEGIN_GRANT_RENEWAL": (
        frozenset({"LIVE"}),
        "PENDING_BOUNDARY_INSTALLATION",
    ),
    "ACTIVATE_PENDING_GRANT": (
        frozenset({"PENDING_BOUNDARY_INSTALLATION"}),
        "LIVE",
    ),
    "TERMINATE_GRANT": (
        frozenset({"PENDING_BOUNDARY_INSTALLATION", "LIVE"}),
        "TERMINAL",
    ),
    "REATTACH_FROM_TERMINAL_GRANT": (
        frozenset({"TERMINAL"}),
        "PENDING_BOUNDARY_INSTALLATION",
    ),
}


def _server_transition_guard(kind: str, prior: str, installed: str) -> None:
    rule = SERVER_TRANSITIONS.get(kind)
    _require(rule is not None, "unknown server transition")
    allowed_prior, expected_installed = rule
    _require(prior in allowed_prior, f"{kind} rejects prior phase {prior}")
    _require(installed == expected_installed, f"{kind} installs wrong phase")


def _validate_plan_and_grant(
    plan: ObserverGrantBoundaryInstallationPlan,
    grant: ObserverGrant,
    full_key: TrustedDeliveryBoundaryGrantKey,
) -> None:
    _require(
        type(plan) is ObserverGrantBoundaryInstallationPlan
        and type(grant) is ObserverGrant
        and type(full_key) is TrustedDeliveryBoundaryGrantKey,
        "plan, grant, or boundary key type is not exact",
    )
    _require(grant.boundary_installation_plan_digest == _digest(plan), "plan mismatch")
    _require(full_key == _full_key(plan, grant), "full boundary key mismatch")
    _require(
        plan.originating_operation
        in {
            "ATTACH_NEW_GRANT_LINEAGE",
            "BEGIN_GRANT_RENEWAL",
            "REATTACH_FROM_TERMINAL_GRANT",
        },
        "plan has an unknown originating operation",
    )
    _require(
        plan.stable_registry_key
        == ObserverGrantRegistryKey(
            grant.requester_principal,
            grant.grant_lineage_incarnation,
        ),
        "stable registry key mismatch",
    )
    _require(
        grant.issuance_sequence == plan.proposed_issuance_sequence,
        "issuance sequence mismatch",
    )
    _require(
        grant.issuance_context_digest == plan.proposed_issuance_context_digest
        and grant.operation_challenge == plan.operation_challenge
        and grant.operation_context_digest == plan.operation_context_digest,
        "grant issuance or operation context drift",
    )
    _require(
        (
            grant.logical_session,
            grant.session_generation,
            grant.descriptor_revision,
            grant.descriptor_digest,
            grant.privacy_policy_digest,
            grant.security_state_digest,
            grant.security_epoch,
            grant.revocation_epoch,
        )
        == (
            plan.logical_session,
            plan.session_generation,
            plan.descriptor_revision,
            plan.descriptor_digest,
            plan.privacy_policy_digest,
            plan.security_state_digest,
            plan.security_epoch,
            plan.revocation_epoch,
        ),
        "grant session, descriptor, privacy, or security mirror drift",
    )
    _require(
        grant.exact_scope_digests == plan.exact_scope_digests
        and plan.exact_scope_digests == tuple(sorted(set(plan.exact_scope_digests)))
        and bool(plan.exact_scope_digests),
        "grant scope set is incomplete, duplicated, or noncanonical",
    )
    _require(
        plan.exact_scope_digests
        == tuple(sorted(member.exact_scope_digest for member in plan.boundary_members)),
        "grant scope set is not the exact canonical boundary scope inventory",
    )
    _require(
        grant.exact_boundary_member_identities
        == tuple(member.identity for member in plan.boundary_members),
        "grant boundary identity drift",
    )
    _require(
        tuple(member.identity for member in plan.boundary_members)
        == tuple(
            sorted(
                {member.identity for member in plan.boundary_members},
                key=_canonical_bytes,
            )
        ),
        "plan boundary inventory is duplicated or noncanonical",
    )
    _require(
        grant.server_deadline_policy_id == plan.server_deadline_policy_id
        and grant.observer_deadline_policy_id == plan.observer_deadline_policy_id,
        "grant deadline-policy mirror drift",
    )
    _require(
        len(plan.boundary_deadlines) == len(plan.boundary_members),
        "boundary deadline/member cardinality mismatch",
    )
    for member, deadline in zip(
        plan.boundary_members,
        plan.boundary_deadlines,
        strict=True,
    ):
        try:
            validate_boundary_membership(
                member.scope_membership,
                scope=member.read_scope,
                expected_boundary_identity=(
                    member.boundary_principal,
                    member.boundary_instance,
                    member.deadline_policy_id,
                ),
            )
        except BridgeValidationError as exc:
            raise ProbeError("boundary read-scope membership is invalid") from exc
        _require(
            (
                member.scope_membership.boundary_principal,
                member.scope_membership.boundary_instance,
                member.scope_membership.delivery_domain,
                member.scope_membership.deadline_policy_id,
            )
            == (
                member.boundary_principal,
                member.boundary_instance,
                member.delivery_domain,
                member.deadline_policy_id,
            ),
            "boundary member identity diverges from its typed scope membership",
        )
        expected = _derive_boundary_deadline(
            member,
            request_time=plan.server_request_time,
            installation_close=plan.server_grant_installation_close,
            grant_not_after=plan.server_grant_not_after,
            minimum_budget=plan.minimum_boundary_activation_budget,
            maximum_lag=plan.maximum_boundary_revocation_lag,
        )
        _require(deadline == expected, "boundary deadline derivation mismatch")
    request_plus_lag = _checked_add(
        plan.server_request_time,
        plan.maximum_boundary_revocation_lag,
    )
    _require(
        _checked_add(
            plan.server_grant_installation_close,
            plan.minimum_boundary_activation_budget,
        )
        <= min(plan.server_grant_not_after, request_plus_lag),
        "server feasibility invariant failed",
    )


@dataclass(frozen=True)
class ServerActivationResult:
    commitment: ObserverGrantBoundaryInstallationCommitment
    set_receipt: ObserverGrantBoundaryInstallationSetReceipt
    entry_proof: ObserverGrantRegistryActivationEntryProof
    attached: ObserverAttached
    installed_ledger_head: ObserverGrantLedgerHead


@dataclass(frozen=True)
class ServerRenewalResult:
    fence_receipt: ObserverGrantRenewalPredecessorFenceReceipt
    installed_pending_head: ObserverGrantLedgerHead


@dataclass(frozen=True)
class ServerTerminalResult:
    transition_fact: ObserverGrantTerminalTransitionFact
    terminal_receipt: ObserverGrantTerminalTransitionReceipt
    reattachment_policy_result: ObserverGrantReattachmentPolicyResult
    installed_terminal_head: ObserverGrantLedgerHead


class ObserverAuthorizationServer:
    """Synthetic server state machine rooted in one outer selector."""

    def __init__(self) -> None:
        (
            self.store,
            self._persistence_recovery_authority,
        ) = AtomicAuthorityStore.enroll(
            store_id="observer-authorization-server",
            authority_principal=SERVER_PRINCIPAL,
            authority_key_id=SERVER_KEY_ID,
            security_state_digest=SECURITY_STATE_DIGEST,
            clock_incarnation=SERVER_CLOCK_1,
            writer_exclusive_not_after=10_000,
        )
        self._read_decision_cache: dict[
            str,
            tuple[str, SealedObserverReadAuthorizationDecision],
        ] = {}

    @property
    def head(self) -> ObserverAuthorizationStateHead:
        state = self.store.snapshot.state
        _require(
            isinstance(state, ObserverAuthorizationStateHead),
            "server is not initialized",
        )
        return state

    def registry(
        self,
        head: ObserverAuthorizationStateHead | None = None,
    ) -> ObserverGrantRegistryHead:
        selected = head or self.head
        return self.store.object(
            selected.observer_grant_registry_head_digest,
            ObserverGrantRegistryHead,
        )

    def entry(
        self,
        key: ObserverGrantRegistryKey,
    ) -> ObserverGrantLedgerHead | None:
        registry = self.registry()
        entry_digest = _tuple_map(registry.entries).get(_digest(key))
        if entry_digest is None:
            return None
        return self.store.object(entry_digest, ObserverGrantLedgerHead)

    def _deadline_intent(
        self,
        *,
        purpose: str,
        kind: str,
        deadline: int,
        transition_kind: str,
        operation_id: str,
        margin: int = 0,
    ) -> AuthorizationDeadlineConditionIntent:
        snapshot = self.store.snapshot
        return _intent(
            purpose,
            kind,
            snapshot.clock_incarnation,
            deadline,
            store_id=snapshot.store_id,
            authority_principal=snapshot.authority_principal,
            transition_kind=transition_kind,
            operation_id=operation_id,
            expected_prior_state_digest=snapshot.state_digest,
            expected_prior_selector_version=snapshot.snapshot_version,
            security_state_digest=snapshot.security_state_digest,
            margin=margin,
        )

    def _install(
        self,
        *,
        transition_kind: str,
        prior_head: ObserverAuthorizationStateHead | None,
        installed_head: ObserverAuthorizationStateHead,
        installed_registry: ObserverGrantRegistryHead,
        prior_entry: ObserverGrantLedgerHead | None,
        installed_entry: ObserverGrantLedgerHead | None,
        objects: Sequence[Any],
        operation_id: str,
        specialized_builder: Callable[
            [
                AtomicReceiptContext,
                ObserverAuthorizationStateCommitReceipt,
                ObserverGrantRegistryCommitReceipt,
                InstalledObserverAuthorizationStateSelector,
            ],
            tuple[Any, ...],
        ],
        commit_time: int,
        deadline_intents: Sequence[AuthorizationDeadlineConditionIntent] = (),
        next_clock_incarnation: str | None = None,
        allocate_state_incarnation: str | None = None,
        fault_cut: str | None = None,
    ) -> AtomicTransitionRecord:
        snapshot = self.store.snapshot
        current = snapshot.state
        _require(current == prior_head, "server prior head is not current")
        _require(
            installed_head.prior_authorization_head_digest
            == (None if prior_head is None else _digest(prior_head)),
            "server successor prior digest mismatch",
        )
        _require(
            installed_head.state_version
            == (1 if prior_head is None else prior_head.state_version + 1),
            "server outer version is not strict",
        )
        prior_registry = None if prior_head is None else self.registry(prior_head)
        _require(
            installed_registry.prior_registry_head_digest
            == (None if prior_registry is None else _digest(prior_registry)),
            "registry successor prior digest mismatch",
        )
        _require(
            installed_registry.state_version
            == (1 if prior_registry is None else prior_registry.state_version + 1),
            "registry version is not strict",
        )
        if installed_entry is not None:
            _require(
                installed_entry.prior_keyed_head_digest
                == (None if prior_entry is None else _digest(prior_entry)),
                "keyed successor prior digest mismatch",
            )
            _require(
                installed_entry.state_version
                == (1 if prior_entry is None else prior_entry.state_version + 1),
                "keyed version is not strict",
            )
        prior_entries = (
            {} if prior_registry is None else _tuple_map(prior_registry.entries)
        )
        installed_entries = _tuple_map(installed_registry.entries)
        changed_key = (
            None if installed_entry is None else _digest(installed_entry.registry_key)
        )
        _require(
            installed_head.observer_grant_registry_head_digest
            == _digest(installed_registry),
            "outer head does not bind installed registry",
        )
        if installed_entry is None:
            _require(
                prior_registry is None and not installed_entries,
                "single-entry transaction has an undeclared registry mutation",
            )
        elif prior_entry is None:
            _require(
                set(installed_entries) == {*prior_entries, changed_key},
                "fresh insertion added or removed an undeclared registry key",
            )
        else:
            _require(
                set(installed_entries) == set(prior_entries),
                "key replacement changed registry key membership",
            )
        for key_digest, prior_digest in prior_entries.items():
            if key_digest != changed_key:
                _require(
                    installed_entries.get(key_digest) == prior_digest,
                    "unrelated server registry sibling changed",
                )
        if installed_entry is not None:
            _require(
                installed_entries.get(changed_key) == _digest(installed_entry),
                "installed keyed head is not registry member",
            )
        intent_tuple = tuple(deadline_intents)
        if installed_entry is not None:
            _require(
                installed_entry.deadline_intent_set_digest
                == (_intent_set_digest(intent_tuple) if intent_tuple else None),
                "keyed successor does not bind its exact deadline intent set",
            )

        def receipt_builder(context: AtomicReceiptContext) -> AtomicReceiptBundle:
            generic = ObserverAuthorizationStateCommitReceipt(
                transition_kind=transition_kind,
                operation_id=context.operation_id,
                operation_commitment_digest=(context.operation_commitment_digest),
                prior_outer_head_digest=(
                    None if prior_head is None else _digest(prior_head)
                ),
                installed_outer_head_digest=_digest(installed_head),
                installed_selector_version=context.selector_version,
                deadline_intent_set_digest=(
                    _intent_set_digest(context.deadline_intents)
                    if context.deadline_intents
                    else None
                ),
                deadline_conditions=context.deadline_conditions,
            )
            selector = InstalledObserverAuthorizationStateSelector(
                state_incarnation=installed_head.state_incarnation,
                selector_version=context.selector_version,
                selected_head_digest=_digest(installed_head),
                generic_commit_receipt_digest=_digest(generic),
            )
            registry_receipt = ObserverGrantRegistryCommitReceipt(
                transition_kind=(
                    "GRANT_REGISTRY_GENESIS_FROM_UNINITIALIZED"
                    if prior_registry is None
                    else transition_kind
                ),
                operation_id=context.operation_id,
                operation_commitment_digest=(context.operation_commitment_digest),
                prior_outer_head_digest=(
                    None if prior_head is None else _digest(prior_head)
                ),
                installed_outer_head_digest=_digest(installed_head),
                outer_commit_receipt_digest=_digest(generic),
                prior_registry_head_digest=(
                    None if prior_registry is None else _digest(prior_registry)
                ),
                installed_registry_head_digest=_digest(installed_registry),
                prior_entry_head_digest=(
                    None if prior_entry is None else _digest(prior_entry)
                ),
                installed_entry_head_digest=(
                    None if installed_entry is None else _digest(installed_entry)
                ),
                installed_selector_version=context.selector_version,
                installed_selector_digest=_digest(selector),
                sibling_preservation_digest=_digest(
                    tuple(
                        sorted(
                            (key, value)
                            for key, value in installed_entries.items()
                            if key != changed_key
                        )
                    )
                ),
            )
            return AtomicReceiptBundle(
                generic_commit_payload=generic,
                selector=selector,
                specialized_payloads=(
                    registry_receipt,
                    *specialized_builder(
                        context,
                        generic,
                        registry_receipt,
                        selector,
                    ),
                ),
            )

        candidate = AtomicCandidate(
            expected_snapshot_version=snapshot.snapshot_version,
            expected_state_digest=snapshot.state_digest,
            state=installed_head,
            objects=(
                *objects,
                installed_registry,
                installed_head,
            ),
            transition_kind=transition_kind,
            operation_id=operation_id,
            deadline_intents=intent_tuple,
            receipt_builder=receipt_builder,
            next_clock_incarnation=next_clock_incarnation,
            allocate_state_incarnation=allocate_state_incarnation,
        )
        return self.store.commit_at_for_test(
            candidate,
            trusted_clock_sample=commit_time,
            fault_cut=fault_cut,
        )

    def genesis(
        self,
        descriptor: ObserverDescriptor,
        *,
        manifest: ObserverDefaultDenyManifest,
        commit_time: int,
        fault_cut: str | None = None,
    ) -> None:
        _validate_default_deny_manifest(manifest)
        _require(
            (
                descriptor.responder_principal,
                descriptor.authority_realm_key,
                descriptor.logical_session,
                descriptor.session_generation,
                descriptor.security_state_digest,
                descriptor.security_epoch,
                descriptor.revocation_epoch,
                manifest.issuer_principal,
                manifest.issuer_key_id,
            )
            == (
                SERVER_PRINCIPAL,
                manifest.authority_realm_key,
                manifest.entries[0].logical_session,
                manifest.entries[0].session_generation,
                manifest.entries[0].security_state_digest,
                manifest.entries[0].security_epoch,
                manifest.entries[0].revocation_epoch,
                SERVER_PRINCIPAL,
                SERVER_KEY_ID,
            ),
            "descriptor and default-deny manifest authority scope diverge",
        )
        allocation = _parent_allocation_receipt(
            store_id=self.store.snapshot.store_id,
            state_incarnation=SERVER_STATE_INCARNATION,
        )
        operation_id = _uuid_for(("server-genesis", allocation))
        if self.store.snapshot.state is not None:
            prior = self.store.transition_for_operation(operation_id)
            objects = _tuple_map(self.store.snapshot.objects)
            _require(
                self.store.snapshot.snapshot_version == 1
                and prior is not None
                and prior.transition_kind
                == "OBSERVER_AUTHORIZATION_STATE_GENESIS_FROM_SESSION_CREATION"
                and prior.installed_state_digest == self.store.snapshot.state_digest
                and objects.get(_digest(allocation)) == allocation
                and objects.get(_digest(descriptor)) == descriptor
                and objects.get(_digest(manifest)) == manifest,
                "server genesis retry differs from the one durable winner",
            )
            return
        registry = ObserverGrantRegistryHead(
            logical_session=SESSION_ID,
            session_generation=SESSION_GENERATION,
            registry_incarnation=REGISTRY_INCARNATION,
            state_version=1,
            prior_registry_head_digest=None,
            entries=(),
            retained_lineage_tombstones=(),
        )
        head = ObserverAuthorizationStateHead(
            server_principal=SERVER_PRINCIPAL,
            authority_realm_key=descriptor.authority_realm_key,
            logical_session=SESSION_ID,
            session_generation=SESSION_GENERATION,
            state_incarnation=SERVER_STATE_INCARNATION,
            state_version=1,
            prior_authorization_head_digest=None,
            descriptor_revision=descriptor.descriptor_revision,
            descriptor_digest=_digest(descriptor),
            privacy_policy_digest=descriptor.privacy_policy_digest,
            security_state_digest=descriptor.security_state_digest,
            security_epoch=descriptor.security_epoch,
            revocation_epoch=descriptor.revocation_epoch,
            default_deny_manifest_digest=_digest(manifest),
            coordinator_clock_policy_id=("SERVER_MONOTONIC_ADVANCES_ACROSS_SUSPEND"),
            coordinator_clock_incarnation=self.store.snapshot.clock_incarnation,
            observer_grant_registry_head_digest=_digest(registry),
            transition_fact_digest=_digest(allocation),
        )
        self._install(
            transition_kind=(
                "OBSERVER_AUTHORIZATION_STATE_GENESIS_FROM_SESSION_CREATION"
            ),
            prior_head=None,
            installed_head=head,
            installed_registry=registry,
            prior_entry=None,
            installed_entry=None,
            objects=(allocation, descriptor, manifest),
            operation_id=operation_id,
            specialized_builder=lambda _context, _generic, _registry, _selector: (),
            commit_time=commit_time,
            allocate_state_incarnation=SERVER_STATE_INCARNATION,
            fault_cut=fault_cut,
        )

    def install_pending(
        self,
        plan: ObserverGrantBoundaryInstallationPlan,
        grant: ObserverGrant,
        *,
        transition_kind: str,
        predecessor_closure_receipt_digest: str | None,
        commit_time: int,
    ) -> ObserverGrantLedgerHead:
        full_key = _full_key(plan, grant)
        _validate_plan_and_grant(plan, grant, full_key)
        prior_outer = self.head
        prior_registry = self.registry()
        prior_entry = self.entry(plan.stable_registry_key)
        descriptor = self.store.object(
            prior_outer.descriptor_digest,
            ObserverDescriptor,
        )
        manifest = self.store.object(
            prior_outer.default_deny_manifest_digest,
            ObserverDefaultDenyManifest,
        )
        _validate_default_deny_manifest(manifest)
        _require(
            (
                plan.logical_session,
                plan.session_generation,
                plan.descriptor_revision,
                plan.descriptor_digest,
                plan.privacy_policy_digest,
                plan.security_state_digest,
                plan.security_epoch,
                plan.revocation_epoch,
                plan.coordinator_clock_incarnation,
            )
            == (
                prior_outer.logical_session,
                prior_outer.session_generation,
                prior_outer.descriptor_revision,
                prior_outer.descriptor_digest,
                prior_outer.privacy_policy_digest,
                prior_outer.security_state_digest,
                prior_outer.security_epoch,
                prior_outer.revocation_epoch,
                prior_outer.coordinator_clock_incarnation,
            ),
            "plan is not current under the selected server descriptor/security/clock",
        )
        _require(
            descriptor.responder_principal == prior_outer.server_principal
            and descriptor.authority_realm_key == prior_outer.authority_realm_key
            and descriptor.security_epoch == prior_outer.security_epoch
            and descriptor.revocation_epoch == prior_outer.revocation_epoch
            and _digest(manifest) == prior_outer.default_deny_manifest_digest
            and descriptor.allowed_boundary_member_identities
            == tuple(member.identity for member in plan.boundary_members),
            "plan boundary inventory is not the current descriptor inventory",
        )
        prior_phase = "ABSENT" if prior_entry is None else prior_entry.phase
        _server_transition_guard(
            transition_kind,
            prior_phase,
            "PENDING_BOUNDARY_INSTALLATION",
        )
        key_digest = _digest(plan.stable_registry_key)
        tombstones = set(prior_registry.retained_lineage_tombstones)
        if prior_entry is None:
            _require(key_digest not in tombstones, "lineage tombstone forbids reuse")
            _require(grant.issuance_sequence == 1, "new lineage must start at one")
            next_sequence = 2
            consumed_heads: tuple[str, ...] = ()
            consumed_fences: tuple[str, ...] = ()
        else:
            _require(
                grant.issuance_sequence == prior_entry.next_issuance_sequence,
                "issuance sequence reset, reuse, or skip",
            )
            _require(
                predecessor_closure_receipt_digest is not None,
                "reattachment requires predecessor authorization closure",
            )
            next_sequence = _checked_add(prior_entry.next_issuance_sequence, 1)
            consumed_heads = (
                *prior_entry.consumed_predecessor_head_digests,
                _digest(prior_entry),
            )
            consumed_fences = prior_entry.consumed_predecessor_fence_digests
        pending = ObserverGrantLedgerHead(
            registry_key=plan.stable_registry_key,
            full_boundary_key=full_key,
            state_version=1 if prior_entry is None else prior_entry.state_version + 1,
            prior_keyed_head_digest=(
                None if prior_entry is None else _digest(prior_entry)
            ),
            phase="PENDING_BOUNDARY_INSTALLATION",
            canonical_grant_digest=_digest(grant),
            boundary_installation_plan_digest=_digest(plan),
            activation_commitment_digest=None,
            renewal_transition_fact_digest=None,
            terminal_transition_fact_digest=None,
            next_issuance_sequence=next_sequence,
            consumed_predecessor_head_digests=consumed_heads,
            consumed_predecessor_fence_digests=consumed_fences,
            effective_server_installation_close=(plan.server_grant_installation_close),
            effective_server_not_after=plan.server_grant_not_after,
            coordinator_clock_incarnation=(plan.coordinator_clock_incarnation),
            clock_restart_ancestry=(),
            distributed_authorization_closure_pending=False,
            deadline_intent_set_digest=None,
        )
        entries = _tuple_map(prior_registry.entries)
        if prior_entry is None:
            _require(key_digest not in entries, "duplicate fresh registry insertion")
        else:
            _require(
                entries.get(key_digest) == _digest(prior_entry),
                "stale keyed predecessor assertion",
            )
        entries[key_digest] = _digest(pending)
        _require(len(entries) <= MAX_GRANTS, "server registry capacity exhausted")
        registry = ObserverGrantRegistryHead(
            logical_session=prior_registry.logical_session,
            session_generation=prior_registry.session_generation,
            registry_incarnation=prior_registry.registry_incarnation,
            state_version=prior_registry.state_version + 1,
            prior_registry_head_digest=_digest(prior_registry),
            entries=tuple(sorted(entries.items())),
            retained_lineage_tombstones=(prior_registry.retained_lineage_tombstones),
        )
        outer = replace(
            prior_outer,
            state_version=prior_outer.state_version + 1,
            prior_authorization_head_digest=_digest(prior_outer),
            observer_grant_registry_head_digest=_digest(registry),
            transition_fact_digest=_digest(plan),
        )
        self._install(
            transition_kind=transition_kind,
            prior_head=prior_outer,
            installed_head=outer,
            installed_registry=registry,
            prior_entry=prior_entry,
            installed_entry=pending,
            objects=(plan, grant, full_key, pending),
            operation_id=_uuid_for(
                (
                    transition_kind,
                    grant.operation_challenge,
                    grant.issuance_sequence,
                )
            ),
            specialized_builder=(
                lambda _context, _generic, _registry, _selector: (grant,)
            ),
            commit_time=commit_time,
        )
        return pending

    def activate(
        self,
        key: ObserverGrantRegistryKey,
        *,
        prepared_boundaries: Sequence[
            tuple[AtomicAuthorityStore, BoundaryPreparationResult]
        ],
        predecessor_closure_receipt_digest: str | None,
        capability_evidence: ObserverReadCapabilityEvidence,
        commit_time: int,
    ) -> ServerActivationResult:
        prior_outer = self.head
        prior_registry = self.registry()
        prior_entry = self.entry(key)
        _require(prior_entry is not None, "activation key is absent")
        _server_transition_guard(
            "ACTIVATE_PENDING_GRANT",
            prior_entry.phase,
            "LIVE",
        )
        plan = self.store.object(
            prior_entry.boundary_installation_plan_digest,
            ObserverGrantBoundaryInstallationPlan,
        )
        grant = self.store.object(
            prior_entry.canonical_grant_digest,
            ObserverGrant,
        )
        _validate_plan_and_grant(plan, grant, prior_entry.full_boundary_key)
        prepared_evidence = _canonical_unique(
            tuple(prepared_boundaries),
            key=lambda item: item[1].fact.boundary_member.identity,
            maximum=MAX_BOUNDARIES,
            label="prepared boundary evidence set",
        )
        prepared_snapshots = tuple(
            boundary_store.snapshot
            for boundary_store, _preparation in prepared_evidence
        )
        _require(
            len(prepared_evidence) == len(plan.boundary_members),
            "prepared boundary evidence set is incomplete or extra",
        )
        _require(
            tuple(item[1].fact.boundary_member.identity for item in prepared_evidence)
            == tuple(member.identity for member in plan.boundary_members),
            "prepared boundary evidence is not a bijection over plan members",
        )
        prepared_pairs: list[tuple[tuple[str, ...], str]] = []
        for boundary_store, preparation in prepared_evidence:
            fact = preparation.fact
            receipt = preparation.enforcement_receipt
            member = fact.boundary_member
            expected_deadline = plan.boundary_deadlines[
                tuple(plan.boundary_members).index(member)
            ]
            _require(
                (
                    fact.full_boundary_key,
                    fact.canonical_grant_digest,
                    fact.boundary_installation_plan_digest,
                    fact.stable_registry_key,
                    fact.deadline,
                    fact.server_pending_outer_head_digest,
                    fact.server_pending_registry_head_digest,
                    fact.server_pending_keyed_head_digest,
                )
                == (
                    prior_entry.full_boundary_key,
                    _digest(grant),
                    _digest(plan),
                    key,
                    expected_deadline,
                    _digest(prior_outer),
                    _digest(prior_registry),
                    _digest(prior_entry),
                ),
                "prepared boundary fact is not for the exact current pending grant",
            )
            _require(
                boundary_store.snapshot.authority_principal == member.boundary_principal
                and boundary_store.snapshot.authority_key_id == member.security_key_id
                and boundary_store.snapshot.security_state_digest
                == member.security_state_digest
                and boundary_store.snapshot.clock_incarnation
                == member.clock_mapping.boundary_clock_incarnation,
                "prepared boundary authority identity/security/clock mismatch",
            )
            _require(
                boundary_store.object(
                    _digest(preparation.installed_entry),
                    TrustedDeliveryBoundaryGrantStateHead,
                )
                == preparation.installed_entry
                and preparation.installed_entry.phase == "PREPARED_BOUNDARY_GRANT"
                and preparation.installed_entry.preparation_fact_digest
                == _digest(fact),
                "prepared boundary entry is absent, stale, or in the wrong phase",
            )
            preparation_transition = boundary_store.transition_for_operation(
                fact.operation_id
            )
            _require(
                preparation_transition is not None
                and _digest(receipt)
                in preparation_transition.specialized_receipt_digests,
                "prepared boundary receipt is not in its winning transition",
            )
            exact_bytes = boundary_store.recover_exact_signed_bytes(_digest(receipt))
            _verify_signed_bytes(
                receipt,
                exact_bytes,
                expected_principal=member.boundary_principal,
                expected_key_id=member.security_key_id,
                expected_security_state=member.security_state_digest,
            )
            _require(
                receipt.preparation_fact_digest == _digest(fact)
                and receipt.installed_entry_head_digest
                == _digest(preparation.installed_entry)
                and receipt.canonical_grant_digest == _digest(grant)
                and receipt.boundary_installation_plan_digest == _digest(plan),
                "prepared boundary receipt does not bind its exact fact/entry/grant",
            )
            prepared_pairs.append((member.identity, _digest(receipt)))
        prepared = tuple(prepared_pairs)
        _require(
            len({item[1] for item in prepared}) == len(prepared),
            "one prepared receipt was reused for multiple members",
        )
        manifest = self.store.object(
            prior_outer.default_deny_manifest_digest,
            ObserverDefaultDenyManifest,
        )
        manifest_entry = _validate_capability_evidence(
            capability_evidence,
            manifest=manifest,
            trusted_time=commit_time,
        )
        read_capability = capability_evidence.capability
        _require(
            read_capability.observer_principal == grant.requester_principal
            and read_capability.manifest_session_scope
            == (grant.logical_session, grant.session_generation)
            and read_capability.authority_realm_key == prior_outer.authority_realm_key
            and read_capability.default_deny_manifest_digest
            == prior_outer.default_deny_manifest_digest
            and read_capability.operations == OBSERVER_READ_OPERATIONS
            and read_capability.exact_scope_digests == grant.exact_scope_digests
            and read_capability.exact_scope_digests
            == _manifest_scope_digests(manifest_entry)
            and read_capability.issued_at >= plan.server_request_time
            and read_capability.not_after <= prior_entry.effective_server_not_after
            and (
                read_capability.security_state_digest,
                read_capability.security_epoch,
                read_capability.revocation_epoch,
                read_capability.coordinator_clock_incarnation,
            )
            == (
                prior_outer.security_state_digest,
                prior_outer.security_epoch,
                prior_outer.revocation_epoch,
                prior_outer.coordinator_clock_incarnation,
            ),
            "observer read capability is cross-principal, cross-session, "
            "cross-manifest, stale, writable, or incomplete",
        )
        operation_id = _uuid_for(
            (
                "server-activate",
                _digest(prior_entry),
                _digest(plan),
                _digest(grant),
                prepared,
            )
        )
        intents = (
            self._deadline_intent(
                purpose=AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE,
                kind="SERVER_GRANT_INSTALLATION_CLOSE",
                deadline=prior_entry.effective_server_installation_close,
                transition_kind="ACTIVATE_PENDING_GRANT",
                operation_id=operation_id,
            ),
            self._deadline_intent(
                purpose=AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE,
                kind="SERVER_GRANT_NOT_AFTER",
                deadline=prior_entry.effective_server_not_after,
                transition_kind="ACTIVATE_PENDING_GRANT",
                operation_id=operation_id,
            ),
        )
        commitment = ObserverGrantBoundaryInstallationCommitment(
            operation_id=operation_id,
            deadline_intent_set_digest=_intent_set_digest(intents),
            boundary_installation_plan_digest=_digest(plan),
            canonical_grant_digest=_digest(grant),
            pending_outer_head_digest=_digest(prior_outer),
            pending_registry_head_digest=_digest(prior_registry),
            pending_keyed_head_digest=_digest(prior_entry),
            canonical_prepared_member_receipts=prepared,
            transition_kind=plan.originating_operation,
            predecessor_closure_receipt_digest=(predecessor_closure_receipt_digest),
        )
        live = replace(
            prior_entry,
            state_version=prior_entry.state_version + 1,
            prior_keyed_head_digest=_digest(prior_entry),
            phase="LIVE",
            activation_commitment_digest=_digest(commitment),
            deadline_intent_set_digest=_intent_set_digest(intents),
        )
        entries = _tuple_map(prior_registry.entries)
        _require(
            entries.get(_digest(key)) == _digest(prior_entry),
            "activation uses stale registry entry",
        )
        entries[_digest(key)] = _digest(live)
        registry = replace(
            prior_registry,
            state_version=prior_registry.state_version + 1,
            prior_registry_head_digest=_digest(prior_registry),
            entries=tuple(sorted(entries.items())),
        )
        outer = replace(
            prior_outer,
            state_version=prior_outer.state_version + 1,
            prior_authorization_head_digest=_digest(prior_outer),
            observer_grant_registry_head_digest=_digest(registry),
            transition_fact_digest=_digest(commitment),
        )

        built: dict[str, Any] = {}

        def specialized_builder(
            context: AtomicReceiptContext,
            generic: ObserverAuthorizationStateCommitReceipt,
            registry_receipt: ObserverGrantRegistryCommitReceipt,
            selector: InstalledObserverAuthorizationStateSelector,
        ) -> tuple[Any, ...]:
            set_receipt = ObserverGrantBoundaryInstallationSetReceipt(
                commitment_digest=_digest(commitment),
                canonical_prepared_member_receipts=prepared,
                prior_outer_head_digest=_digest(prior_outer),
                installed_outer_head_digest=_digest(outer),
                prior_registry_head_digest=_digest(prior_registry),
                installed_registry_head_digest=_digest(registry),
                prior_keyed_head_digest=_digest(prior_entry),
                installed_keyed_head_digest=_digest(live),
                installed_selector_version=context.selector_version,
                installed_selector_digest=_digest(selector),
                outer_commit_receipt_digest=_digest(generic),
                registry_commit_receipt_digest=_digest(registry_receipt),
                deadline_intent_set_digest=_intent_set_digest(context.deadline_intents),
                deadline_conditions=context.deadline_conditions,
            )
            proof = ObserverGrantRegistryActivationEntryProof(
                stable_registry_key=key,
                full_boundary_key=live.full_boundary_key,
                installed_outer_head_digest=_digest(outer),
                installed_registry_head_digest=_digest(registry),
                installed_keyed_head_digest=_digest(live),
                boundary_installation_set_receipt_digest=_digest(set_receipt),
                membership_path_digest=_digest(
                    (
                        outer.observer_grant_registry_head_digest,
                        _digest(live),
                    )
                ),
                installed_selector_version=context.selector_version,
                installed_selector_digest=_digest(selector),
                outer_commit_receipt_digest=_digest(generic),
            )
            attached = ObserverAttached(
                descriptor_digest=outer.descriptor_digest,
                canonical_grant_digest=live.canonical_grant_digest,
                boundary_installation_set_receipt_digest=_digest(set_receipt),
                observer_read_capability_digest=_digest(read_capability),
                installed_selector_version=context.selector_version,
                installed_selector_digest=_digest(selector),
                outer_commit_receipt_digest=_digest(generic),
            )
            built.update(
                {
                    "set_receipt": set_receipt,
                    "proof": proof,
                    "attached": attached,
                }
            )
            return set_receipt, proof, attached

        self._install(
            transition_kind="ACTIVATE_PENDING_GRANT",
            prior_head=prior_outer,
            installed_head=outer,
            installed_registry=registry,
            prior_entry=prior_entry,
            installed_entry=live,
            objects=(
                commitment,
                live,
                capability_evidence.verified_transport_context,
                read_capability,
                capability_evidence.seal,
                capability_evidence.issuer_snapshot,
                capability_evidence,
                *prepared_snapshots,
                *intents,
            ),
            operation_id=operation_id,
            specialized_builder=specialized_builder,
            commit_time=commit_time,
            deadline_intents=intents,
        )
        set_receipt = built["set_receipt"]
        proof = built["proof"]
        attached = built["attached"]
        _require(
            isinstance(set_receipt, ObserverGrantBoundaryInstallationSetReceipt)
            and isinstance(proof, ObserverGrantRegistryActivationEntryProof)
            and isinstance(attached, ObserverAttached),
            "activation receipt factory did not run",
        )
        return ServerActivationResult(
            commitment=commitment,
            set_receipt=set_receipt,
            entry_proof=proof,
            attached=attached,
            installed_ledger_head=live,
        )

    def authorize_read(
        self,
        capability_evidence: ObserverReadCapabilityEvidence,
        *,
        live_transport_context: VerifiedObserverTransportPrincipal,
        read_scope: CanonicalObserverReadScope,
        boundary_membership: ObserverBoundaryReadScopeMembership,
        expected_boundary_identity: tuple[str, str, str],
        observer_instance: str,
        caller_operation_id: str,
        trusted_time: int,
    ) -> SealedObserverReadAuthorizationDecision:
        """Authorize one read against current issuer, transport, and server state."""
        try:
            validate_boundary_membership(
                boundary_membership,
                scope=read_scope,
                expected_boundary_identity=expected_boundary_identity,
            )
        except BridgeValidationError as exc:
            raise ProbeError("read request scope/membership is invalid") from exc
        operation = read_scope.operation
        exact_scope_digest = read_scope.scope_digest
        _validate_atomic_snapshot(self.store.snapshot)
        head = self.head
        manifest = self.store.object(
            head.default_deny_manifest_digest,
            ObserverDefaultDenyManifest,
        )
        entry = _validate_capability_evidence(
            capability_evidence,
            manifest=manifest,
            trusted_time=trusted_time,
        )
        _require(
            type(live_transport_context) is VerifiedObserverTransportPrincipal
            and live_transport_context
            == capability_evidence.verified_transport_context,
            "capability is copied to a different live transport context",
        )
        capability = capability_evidence.capability
        _require(
            type(operation) is str
            and operation in capability.operations
            and operation in entry.operations
            and operation not in OBSERVER_WRITE_OR_AUTHORITY_OPERATIONS,
            "observer operation is unknown, writable, or not manifest-authorized",
        )
        _require(
            _is_hex64(exact_scope_digest)
            and exact_scope_digest in capability.exact_scope_digests
            and exact_scope_digest in _manifest_scope_digests(entry),
            "observer read scope is absent from the exact default-deny grant",
        )
        matching_scopes = tuple(
            scope
            for scope in entry.read_scopes
            if scope.scope_digest == exact_scope_digest
        )
        _require(
            len(matching_scopes) == 1 and matching_scopes[0].operation == operation,
            "observer operation does not match the literal manifest scope",
        )
        _require(
            (
                capability.authority_realm_key,
                capability.manifest_session_scope,
                capability.default_deny_manifest_digest,
                capability.security_state_digest,
                capability.security_epoch,
                capability.revocation_epoch,
                capability.coordinator_clock_incarnation,
            )
            == (
                head.authority_realm_key,
                (head.logical_session, head.session_generation),
                head.default_deny_manifest_digest,
                head.security_state_digest,
                head.security_epoch,
                head.revocation_epoch,
                head.coordinator_clock_incarnation,
            ),
            "capability is stale across realm, session, manifest, security, "
            "revocation, or clock state",
        )
        objects = _tuple_map(self.store.snapshot.objects)
        attached_matches = tuple(
            item
            for item in objects.values()
            if type(item) is ObserverAttached
            and item.observer_read_capability_digest == _digest(capability)
        )
        _require(
            len(attached_matches) == 1,
            "capability has no unique server-issued attachment receipt",
        )
        attached = attached_matches[0]
        signed = _tuple_map(self.store.snapshot.signed_bytes)
        _verify_signed_bytes(
            attached,
            signed.get(_digest(attached), b""),
            expected_principal=SERVER_PRINCIPAL,
            expected_key_id=SERVER_KEY_ID,
            expected_security_state=head.security_state_digest,
        )
        grant = objects.get(attached.canonical_grant_digest)
        _require(type(grant) is ObserverGrant, "attached capability grant is absent")
        plan = objects.get(grant.boundary_installation_plan_digest)
        _require(
            type(plan) is ObserverGrantBoundaryInstallationPlan,
            "attached capability grant plan is absent",
        )
        matching_members = tuple(
            member
            for member in plan.boundary_members
            if member.read_scope == read_scope
            and member.scope_membership == boundary_membership
        )
        _require(
            len(matching_members) == 1,
            "read decision lacks one exact canonical boundary scope membership",
        )
        registry = self.registry()
        ledger_digest = _tuple_map(registry.entries).get(
            _digest(
                ObserverGrantRegistryKey(
                    grant.requester_principal,
                    grant.grant_lineage_incarnation,
                )
            )
        )
        ledger = objects.get(ledger_digest or "")
        _require(
            type(ledger) is ObserverGrantLedgerHead
            and ledger.phase == "LIVE"
            and ledger.canonical_grant_digest == _digest(grant)
            and grant.requester_principal == capability.observer_principal
            and grant.logical_session == capability.manifest_session_scope[0]
            and grant.session_generation == capability.manifest_session_scope[1]
            and grant.security_state_digest == capability.security_state_digest
            and grant.security_epoch == capability.security_epoch
            and grant.revocation_epoch == capability.revocation_epoch
            and exact_scope_digest in grant.exact_scope_digests,
            "capability grant is terminal, replaced, stale, or scope-incongruent",
        )
        _require(
            _safe_int(trusted_time)
            and trusted_time < ledger.effective_server_not_after,
            "observer grant is at or after its exclusive server deadline",
        )
        ingress_context = seal_authorization_ingress_context(
            SyntheticVerifiedAuthorizationIngressContext(
                provenance_kind=("SYNTHETIC_VERIFIED_AUTHORIZATION_SERVER_INGRESS"),
                observer_principal=capability.observer_principal,
                observer_instance=observer_instance,
                authorization_audience=live_transport_context.audience,
                endpoint_profile=live_transport_context.endpoint_profile,
                connection_instance=live_transport_context.connection_instance,
                replay_domain=live_transport_context.replay_domain,
                manifest_digest=_digest(manifest),
                security_state_digest=head.security_state_digest,
                security_epoch=head.security_epoch,
                revocation_epoch=head.revocation_epoch,
                coordinator_clock_incarnation=(head.coordinator_clock_incarnation),
                verified_at=live_transport_context.verified_at,
                exclusive_not_after=live_transport_context.not_after,
                semantic_context_digest="",
                fixture_authentication_tag="",
            ),
            fixture_key=_READ_DECISION_SEAL_KEY,
        )
        caller_request_digest = canonical_read_request_digest(
            scope=read_scope,
            membership=boundary_membership,
            caller_operation_id=caller_operation_id,
            expected_boundary_identity=expected_boundary_identity,
        )
        exclusive_not_after = min(
            capability.not_after,
            live_transport_context.not_after,
            ledger.effective_server_not_after,
        )
        authorization_cut = ExpectedObserverReadAuthorizationCut(
            authorization_ingress_artifact_digest=(
                authorization_ingress_artifact_digest(ingress_context)
            ),
            authorization_endpoint_profile=live_transport_context.endpoint_profile,
            authorization_connection_instance=(
                live_transport_context.connection_instance
            ),
            authorization_replay_domain=live_transport_context.replay_domain,
            capability_digest=_digest(capability),
            capability_seal_digest=_digest(capability_evidence.seal),
            capability_issuer_snapshot_digest=_digest(
                capability_evidence.issuer_snapshot
            ),
            manifest_digest=_digest(manifest),
            manifest_entry_digest=_digest(entry),
            stable_grant_key_digest=_digest(ledger.registry_key),
            full_boundary_key_digest=_digest(ledger.full_boundary_key),
            grant_digest=_digest(grant),
            server_entry_head_digest=_digest(ledger),
            server_selector_digest=self.store.snapshot.transitions[-1].selector_digest,
            authority_realm_key=head.authority_realm_key,
            source_session_kind=read_scope.source_session_kind,
            logical_session_id=head.logical_session,
            source_generation=head.session_generation,
            security_state_digest=head.security_state_digest,
            security_epoch=head.security_epoch,
            revocation_epoch=head.revocation_epoch,
            coordinator_clock_incarnation=head.coordinator_clock_incarnation,
            exclusive_not_after=exclusive_not_after,
            maximum_release_count=1,
        )
        cached = self._read_decision_cache.get(caller_operation_id)
        if cached is not None:
            cached_request_digest, cached_decision = cached
            _require(
                cached_request_digest == caller_request_digest
                and cached_decision.server_entry_head_digest == _digest(ledger)
                and cached_decision.grant_digest == _digest(grant)
                and cached_decision.manifest_digest == _digest(manifest)
                and authorization_ingress_artifact_digest(
                    cached_decision.authorization_ingress_context
                )
                == authorization_ingress_artifact_digest(ingress_context)
                and trusted_time < cached_decision.exclusive_not_after,
                "caller operation ID was reused for different or stale read state",
            )
            return cached_decision
        decision = seal_read_decision(
            SealedObserverReadAuthorizationDecision(
                decision_id=_uuid_for(
                    (
                        "observer-read-decision",
                        caller_operation_id,
                        caller_request_digest,
                    )
                ),
                decision_kind=(
                    "BOUNDED_HISTORY_RESULT"
                    if operation == "history_query"
                    else "LIVE_SUBSCRIPTION_RELEASE"
                ),
                authority_effect=NO_FUTURE_AUTHORITY,
                caller_operation_id=caller_operation_id,
                caller_request_digest=caller_request_digest,
                capability_digest=_digest(capability),
                capability_seal_digest=_digest(capability_evidence.seal),
                capability_issuer_snapshot_digest=_digest(
                    capability_evidence.issuer_snapshot
                ),
                observer_principal=capability.observer_principal,
                observer_instance=observer_instance,
                authorization_ingress_context=ingress_context,
                manifest_digest=_digest(manifest),
                manifest_entry_digest=_digest(entry),
                canonical_scope_digest=exact_scope_digest,
                boundary_scope_membership_digest=(
                    boundary_membership.membership_digest
                ),
                stable_grant_key_digest=_digest(ledger.registry_key),
                full_boundary_key_digest=_digest(ledger.full_boundary_key),
                grant_digest=_digest(grant),
                server_entry_head_digest=_digest(ledger),
                server_selector_digest=self.store.snapshot.transitions[
                    -1
                ].selector_digest,
                authority_realm_key=head.authority_realm_key,
                source_session_kind=read_scope.source_session_kind,
                logical_session_id=head.logical_session,
                source_generation=head.session_generation,
                security_state_digest=head.security_state_digest,
                security_epoch=head.security_epoch,
                revocation_epoch=head.revocation_epoch,
                coordinator_clock_incarnation=head.coordinator_clock_incarnation,
                checked_at=trusted_time,
                exclusive_not_after=exclusive_not_after,
                history_request_digest=(
                    canonical_history_request_digest(read_scope)
                    if operation == "history_query"
                    else None
                ),
                maximum_release_count=1,
                issuer_principal=SERVER_PRINCIPAL,
                issuer_key_id=SERVER_KEY_ID,
                issuer_incarnation=SERVER_STATE_INCARNATION,
                semantic_decision_digest="",
                fixture_authentication_tag="",
            ),
            fixture_key=_READ_DECISION_SEAL_KEY,
        )
        try:
            validate_read_decision(
                decision,
                scope=read_scope,
                membership=boundary_membership,
                expected_boundary_identity=expected_boundary_identity,
                expected_observer_identity=(
                    capability.observer_principal,
                    observer_instance,
                ),
                expected_authorization_audience=read_scope.authorization_audience,
                expected_authorization_cut=authorization_cut,
                expected_issuer_identity=(
                    SERVER_PRINCIPAL,
                    SERVER_KEY_ID,
                    SERVER_STATE_INCARNATION,
                ),
                fixture_key=_READ_DECISION_SEAL_KEY,
            )
        except BridgeValidationError as exc:
            raise ProbeError("sealed read decision failed canonical replay") from exc
        self._read_decision_cache[caller_operation_id] = (
            caller_request_digest,
            decision,
        )
        return decision

    def begin_renewal(
        self,
        plan: ObserverGrantBoundaryInstallationPlan,
        grant: ObserverGrant,
        *,
        g0_activation: ServerActivationResult,
        commit_time: int,
    ) -> ServerRenewalResult:
        full_key = _full_key(plan, grant)
        _validate_plan_and_grant(plan, grant, full_key)
        prior_outer = self.head
        prior_registry = self.registry()
        prior_entry = self.entry(plan.stable_registry_key)
        _require(prior_entry is not None, "renewal predecessor is absent")
        _server_transition_guard(
            "BEGIN_GRANT_RENEWAL",
            prior_entry.phase,
            "PENDING_BOUNDARY_INSTALLATION",
        )
        _require(
            g0_activation.installed_ledger_head == prior_entry,
            "renewal uses stale or cross-grant G0 activation",
        )
        _require(
            g0_activation.set_receipt.installed_keyed_head_digest
            == _digest(prior_entry),
            "G0 set receipt does not install the consumed live head",
        )
        _require(
            g0_activation.entry_proof.boundary_installation_set_receipt_digest
            == _digest(g0_activation.set_receipt),
            "G0 activation proof does not bind its set receipt",
        )
        for payload in (
            g0_activation.set_receipt,
            g0_activation.entry_proof,
        ):
            blob = self.store.recover_exact_signed_bytes(_digest(payload))
            _verify_signed_bytes(
                payload,
                blob,
                expected_principal=SERVER_PRINCIPAL,
                expected_key_id=SERVER_KEY_ID,
                expected_security_state=SECURITY_STATE_DIGEST,
            )
        _require(
            grant.issuance_sequence == prior_entry.next_issuance_sequence,
            "renewal issuance sequence is not strictly next",
        )
        operation_id = _uuid_for(
            (
                "begin-renewal",
                _digest(prior_entry),
                _digest(grant),
            )
        )
        intents = (
            self._deadline_intent(
                purpose=AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE,
                kind="SERVER_GRANT_NOT_AFTER",
                deadline=prior_entry.effective_server_not_after,
                transition_kind="BEGIN_GRANT_RENEWAL",
                operation_id=operation_id,
            ),
        )
        renewal_fact = ObserverGrantRenewalTransitionFact(
            operation_id=operation_id,
            stable_registry_key=plan.stable_registry_key,
            prior_outer_head_digest=_digest(prior_outer),
            prior_registry_head_digest=_digest(prior_registry),
            prior_g0_keyed_head_digest=_digest(prior_entry),
            candidate_plan_digest=_digest(plan),
            candidate_grant_digest=_digest(grant),
            candidate_full_boundary_key=full_key,
            expected_prior_selector_version=(self.store.snapshot.snapshot_version),
            deadline_intent_set_digest=_intent_set_digest(intents),
        )
        pending = ObserverGrantLedgerHead(
            registry_key=prior_entry.registry_key,
            full_boundary_key=full_key,
            state_version=prior_entry.state_version + 1,
            prior_keyed_head_digest=_digest(prior_entry),
            phase="PENDING_BOUNDARY_INSTALLATION",
            canonical_grant_digest=_digest(grant),
            boundary_installation_plan_digest=_digest(plan),
            activation_commitment_digest=None,
            renewal_transition_fact_digest=_digest(renewal_fact),
            terminal_transition_fact_digest=None,
            next_issuance_sequence=_checked_add(
                prior_entry.next_issuance_sequence,
                1,
            ),
            consumed_predecessor_head_digests=(
                *prior_entry.consumed_predecessor_head_digests,
                _digest(prior_entry),
            ),
            consumed_predecessor_fence_digests=(
                prior_entry.consumed_predecessor_fence_digests
            ),
            effective_server_installation_close=(plan.server_grant_installation_close),
            effective_server_not_after=plan.server_grant_not_after,
            coordinator_clock_incarnation=(plan.coordinator_clock_incarnation),
            clock_restart_ancestry=(),
            distributed_authorization_closure_pending=False,
            deadline_intent_set_digest=_intent_set_digest(intents),
        )
        entries = _tuple_map(prior_registry.entries)
        stable_digest = _digest(plan.stable_registry_key)
        _require(
            entries.get(stable_digest) == _digest(prior_entry),
            "renewal predecessor is not the current stable-key value",
        )
        entries[stable_digest] = _digest(pending)
        registry = replace(
            prior_registry,
            state_version=prior_registry.state_version + 1,
            prior_registry_head_digest=_digest(prior_registry),
            entries=tuple(sorted(entries.items())),
        )
        outer = replace(
            prior_outer,
            state_version=prior_outer.state_version + 1,
            prior_authorization_head_digest=_digest(prior_outer),
            observer_grant_registry_head_digest=_digest(registry),
            transition_fact_digest=_digest(renewal_fact),
        )
        built: dict[str, Any] = {}

        def specialized_builder(
            context: AtomicReceiptContext,
            generic: ObserverAuthorizationStateCommitReceipt,
            registry_receipt: ObserverGrantRegistryCommitReceipt,
            selector: InstalledObserverAuthorizationStateSelector,
        ) -> tuple[Any, ...]:
            fence = ObserverGrantRenewalPredecessorFenceReceipt(
                stable_registry_key=plan.stable_registry_key,
                g0_full_boundary_key=prior_entry.full_boundary_key,
                g1_full_boundary_key=full_key,
                consumed_g0_keyed_head_digest=_digest(prior_entry),
                installed_g1_pending_keyed_head_digest=_digest(pending),
                prior_registry_head_digest=_digest(prior_registry),
                installed_registry_head_digest=_digest(registry),
                prior_outer_head_digest=_digest(prior_outer),
                installed_outer_head_digest=_digest(outer),
                installed_selector_version=context.selector_version,
                installed_selector_digest=_digest(selector),
                outer_commit_receipt_digest=_digest(generic),
                registry_commit_receipt_digest=_digest(registry_receipt),
                g0_installation_commitment_digest=_digest(g0_activation.commitment),
                g0_installation_set_receipt_digest=_digest(g0_activation.set_receipt),
                g0_registry_activation_entry_proof_digest=_digest(
                    g0_activation.entry_proof
                ),
                deadline_intent_digest=_digest(context.deadline_intents[0]),
                deadline_condition=context.deadline_conditions[0],
            )
            built["fence"] = fence
            return grant, fence

        self._install(
            transition_kind="BEGIN_GRANT_RENEWAL",
            prior_head=prior_outer,
            installed_head=outer,
            installed_registry=registry,
            prior_entry=prior_entry,
            installed_entry=pending,
            objects=(
                plan,
                grant,
                full_key,
                renewal_fact,
                pending,
                *intents,
            ),
            operation_id=operation_id,
            specialized_builder=specialized_builder,
            commit_time=commit_time,
            deadline_intents=intents,
        )
        fence = built["fence"]
        _require(
            isinstance(fence, ObserverGrantRenewalPredecessorFenceReceipt),
            "renewal receipt factory did not run",
        )
        return ServerRenewalResult(
            fence_receipt=fence,
            installed_pending_head=pending,
        )

    def terminate(
        self,
        key: ObserverGrantRegistryKey,
        *,
        terminal_reason: str,
        actor_or_event: str,
        policy_rule_digest: str,
        policy_inputs_digest: str,
        authority_source_receipt_digest: str,
        failure_evidence: tuple[
            ObserverGrantBoundaryInstallationFailureMemberEvidence, ...
        ] = (),
        commit_time: int,
        expiry: bool = False,
    ) -> ServerTerminalResult:
        _require(
            type(terminal_reason) is str and terminal_reason == "EXPIRED",
            "this probe hard-denies terminal causes without typed authority evidence",
        )
        _require(
            type(expiry) is bool and expiry,
            "EXPIRED requires the exact commit-time expiry predicate",
        )
        _require(
            type(actor_or_event) is str
            and actor_or_event == "trusted-clock-expiry"
            and type(policy_rule_digest) is str
            and policy_rule_digest == _SERVER_EXPIRY_POLICY_RULE_DIGEST
            and type(policy_inputs_digest) is str
            and policy_inputs_digest == _SERVER_EXPIRY_POLICY_INPUTS_DIGEST
            and type(authority_source_receipt_digest) is str
            and authority_source_receipt_digest
            == _SERVER_EXPIRY_AUTHORITY_SOURCE_RECEIPT_DIGEST
            and type(failure_evidence) is tuple
            and not failure_evidence,
            "server expiry cause evidence is not the closed synthetic authority cut",
        )
        prior_outer = self.head
        prior_registry = self.registry()
        prior_entry = self.entry(key)
        _require(prior_entry is not None, "terminal key is absent")
        _server_transition_guard(
            "TERMINATE_GRANT",
            prior_entry.phase,
            "TERMINAL",
        )
        plan = self.store.object(
            prior_entry.boundary_installation_plan_digest,
            ObserverGrantBoundaryInstallationPlan,
        )
        operation_id = _uuid_for(
            (
                "server-terminal",
                _digest(prior_entry),
                terminal_reason,
                actor_or_event,
            )
        )
        intents: tuple[AuthorizationDeadlineConditionIntent, ...] = ()
        if expiry:
            _require(terminal_reason == "EXPIRED", "expiry reason mismatch")
            intents = (
                self._deadline_intent(
                    purpose=EXPIRY_AT_OR_AFTER_EXCLUSIVE_DEADLINE,
                    kind="SERVER_GRANT_NOT_AFTER",
                    deadline=prior_entry.effective_server_not_after,
                    transition_kind="TERMINATE_GRANT",
                    operation_id=operation_id,
                ),
            )
        fact = ObserverGrantTerminalTransitionFact(
            stable_registry_key=key,
            prior_outer_head_digest=_digest(prior_outer),
            prior_registry_head_digest=_digest(prior_registry),
            prior_keyed_head_digest=_digest(prior_entry),
            full_boundary_key=prior_entry.full_boundary_key,
            complete_boundary_member_identities=tuple(
                member.identity for member in plan.boundary_members
            ),
            terminal_reason=terminal_reason,
            actor_or_event=actor_or_event,
            authority_clock_incarnation=prior_outer.coordinator_clock_incarnation,
            reattachment_policy_rule_digest=policy_rule_digest,
            reattachment_policy_inputs_digest=policy_inputs_digest,
            boundary_failure_evidence=tuple(failure_evidence),
            deadline_intent_digest=(_intent_set_digest(intents) if intents else None),
        )
        terminal = replace(
            prior_entry,
            state_version=prior_entry.state_version + 1,
            prior_keyed_head_digest=_digest(prior_entry),
            phase="TERMINAL",
            terminal_transition_fact_digest=_digest(fact),
            distributed_authorization_closure_pending=True,
            deadline_intent_set_digest=(
                _intent_set_digest(intents) if intents else None
            ),
        )
        entries = _tuple_map(prior_registry.entries)
        stable_digest = _digest(key)
        _require(
            entries.get(stable_digest) == _digest(prior_entry),
            "server terminal predecessor is stale",
        )
        entries[stable_digest] = _digest(terminal)
        registry = replace(
            prior_registry,
            state_version=prior_registry.state_version + 1,
            prior_registry_head_digest=_digest(prior_registry),
            entries=tuple(sorted(entries.items())),
        )
        outer = replace(
            prior_outer,
            state_version=prior_outer.state_version + 1,
            prior_authorization_head_digest=_digest(prior_outer),
            observer_grant_registry_head_digest=_digest(registry),
            transition_fact_digest=_digest(fact),
        )
        outcome = (
            "REATTACH_FORBIDDEN"
            if terminal_reason
            in {
                "REVOKED",
                "SECURITY_REBOUND",
                "SESSION_RETIRED",
                "AUTHORITY_CLOCK_DISCONTINUITY",
            }
            else "REATTACH_ALLOWED"
        )
        built: dict[str, Any] = {}

        def specialized_builder(
            context: AtomicReceiptContext,
            generic: ObserverAuthorizationStateCommitReceipt,
            registry_receipt: ObserverGrantRegistryCommitReceipt,
            selector: InstalledObserverAuthorizationStateSelector,
        ) -> tuple[Any, ...]:
            receipt = ObserverGrantTerminalTransitionReceipt(
                transition_fact_digest=_digest(fact),
                prior_outer_head_digest=_digest(prior_outer),
                installed_outer_head_digest=_digest(outer),
                prior_registry_head_digest=_digest(prior_registry),
                installed_registry_head_digest=_digest(registry),
                prior_keyed_head_digest=_digest(prior_entry),
                installed_keyed_head_digest=_digest(terminal),
                installed_selector_version=context.selector_version,
                installed_selector_digest=_digest(selector),
                outer_commit_receipt_digest=_digest(generic),
                registry_commit_receipt_digest=_digest(registry_receipt),
                deadline_conditions=context.deadline_conditions,
            )
            result_key = _digest((_digest(receipt), policy_rule_digest))
            policy_result = ObserverGrantReattachmentPolicyResult(
                installed_terminal_keyed_head_digest=_digest(terminal),
                terminal_transition_receipt_digest=_digest(receipt),
                policy_rule_digest=policy_rule_digest,
                requester_lineage_digest=_digest(key),
                terminal_reason=terminal_reason,
                descriptor_security_scope_digest=_digest(
                    (
                        prior_outer.descriptor_digest,
                        prior_outer.security_state_digest,
                    )
                ),
                policy_inputs_digest=policy_inputs_digest,
                deterministic_evaluator_digest=hashlib.sha256(
                    b"observer-reattachment-evaluator-v1"
                ).hexdigest(),
                authority_source_receipt_digest=authority_source_receipt_digest,
                outcome=outcome,
                unique_result_key=result_key,
                installed_selector_version=context.selector_version,
                installed_selector_digest=_digest(selector),
                outer_commit_receipt_digest=_digest(generic),
            )
            built.update({"receipt": receipt, "policy": policy_result})
            return receipt, policy_result

        self._install(
            transition_kind="TERMINATE_GRANT",
            prior_head=prior_outer,
            installed_head=outer,
            installed_registry=registry,
            prior_entry=prior_entry,
            installed_entry=terminal,
            objects=(fact, terminal, *intents),
            operation_id=operation_id,
            specialized_builder=specialized_builder,
            commit_time=commit_time,
            deadline_intents=intents,
        )
        receipt = built["receipt"]
        policy_result = built["policy"]
        _require(
            isinstance(receipt, ObserverGrantTerminalTransitionReceipt)
            and isinstance(policy_result, ObserverGrantReattachmentPolicyResult),
            "terminal receipt factory did not run",
        )
        return ServerTerminalResult(
            transition_fact=fact,
            terminal_receipt=receipt,
            reattachment_policy_result=policy_result,
            installed_terminal_head=terminal,
        )

    def restart_clock(
        self,
        *,
        new_clock_incarnation: str,
        restart_mapping: AuthenticatedClockMapping,
        commit_time: int,
    ) -> ObserverAuthorizationClockRestartCommitReceipt:
        prior_outer = self.head
        prior_registry = self.registry()
        entries = _tuple_map(prior_registry.entries)
        new_entries = dict(entries)
        mapped_pairs: list[tuple[str, int, int, int, int]] = []
        installed_ledgers: list[ObserverGrantLedgerHead] = []
        _validate_mapping(restart_mapping)
        _require(
            restart_mapping.coordinator_clock_incarnation
            == prior_outer.coordinator_clock_incarnation
            and restart_mapping.boundary_clock_incarnation == new_clock_incarnation,
            "server restart mapping clock identity mismatch",
        )
        for stable_digest, entry_digest in sorted(entries.items()):
            prior_entry = self.store.object(entry_digest, ObserverGrantLedgerHead)
            _require(
                prior_entry.coordinator_clock_incarnation
                == prior_outer.coordinator_clock_incarnation,
                "server restart sees mixed clock ancestry",
            )
            mapped_installation_close = _map_lower(
                restart_mapping,
                prior_entry.effective_server_installation_close,
            )
            mapped_not_after = _map_lower(
                restart_mapping,
                prior_entry.effective_server_not_after,
            )
            _require(
                _clock_le(
                    new_clock_incarnation,
                    mapped_installation_close,
                    new_clock_incarnation,
                    mapped_not_after,
                ),
                "server restart mapped deadline order inverted",
            )
            mapped_pairs.append(
                (
                    stable_digest,
                    prior_entry.effective_server_installation_close,
                    mapped_installation_close,
                    prior_entry.effective_server_not_after,
                    mapped_not_after,
                )
            )
        affected = tuple(item[0] for item in mapped_pairs)
        fact = ObserverAuthorizationClockRestartTransitionFact(
            prior_outer_head_digest=_digest(prior_outer),
            prior_clock_incarnation=prior_outer.coordinator_clock_incarnation,
            new_clock_incarnation=new_clock_incarnation,
            authenticated_restart_mapping=restart_mapping,
            affected_registry_keys=affected,
            mapped_deadline_pairs=tuple(mapped_pairs),
            complete_restart_ancestry_digest=_digest(
                (
                    prior_outer.coordinator_clock_incarnation,
                    new_clock_incarnation,
                    tuple(mapped_pairs),
                )
            ),
        )
        for stable_digest, entry_digest in sorted(entries.items()):
            prior_entry = self.store.object(entry_digest, ObserverGrantLedgerHead)
            mapped_installation_close = _map_lower(
                restart_mapping,
                prior_entry.effective_server_installation_close,
            )
            mapped_not_after = _map_lower(
                restart_mapping,
                prior_entry.effective_server_not_after,
            )
            installed = replace(
                prior_entry,
                state_version=prior_entry.state_version + 1,
                prior_keyed_head_digest=_digest(prior_entry),
                coordinator_clock_incarnation=new_clock_incarnation,
                effective_server_installation_close=mapped_installation_close,
                effective_server_not_after=mapped_not_after,
                clock_restart_ancestry=(
                    *prior_entry.clock_restart_ancestry,
                    _digest(fact),
                ),
            )
            new_entries[stable_digest] = _digest(installed)
            installed_ledgers.append(installed)
        registry = replace(
            prior_registry,
            state_version=prior_registry.state_version + 1,
            prior_registry_head_digest=_digest(prior_registry),
            entries=tuple(sorted(new_entries.items())),
        )
        outer = replace(
            prior_outer,
            state_version=prior_outer.state_version + 1,
            prior_authorization_head_digest=_digest(prior_outer),
            coordinator_clock_incarnation=new_clock_incarnation,
            observer_grant_registry_head_digest=_digest(registry),
            transition_fact_digest=_digest(fact),
        )
        snapshot = self.store.snapshot
        operation_id = _uuid_for(
            (
                "server-clock-restart",
                snapshot.state_digest,
                new_clock_incarnation,
            )
        )
        built: dict[str, Any] = {}

        def receipt_builder(context: AtomicReceiptContext) -> AtomicReceiptBundle:
            generic = ObserverAuthorizationStateCommitReceipt(
                transition_kind="OBSERVER_AUTHORIZATION_CLOCK_RESTART",
                operation_id=context.operation_id,
                operation_commitment_digest=(context.operation_commitment_digest),
                prior_outer_head_digest=_digest(prior_outer),
                installed_outer_head_digest=_digest(outer),
                installed_selector_version=context.selector_version,
                deadline_intent_set_digest=None,
                deadline_conditions=(),
            )
            selector = InstalledObserverAuthorizationStateSelector(
                state_incarnation=outer.state_incarnation,
                selector_version=context.selector_version,
                selected_head_digest=_digest(outer),
                generic_commit_receipt_digest=_digest(generic),
            )
            registry_receipt = ObserverGrantRegistryCommitReceipt(
                transition_kind="OBSERVER_AUTHORIZATION_CLOCK_RESTART",
                operation_id=context.operation_id,
                operation_commitment_digest=(context.operation_commitment_digest),
                prior_outer_head_digest=_digest(prior_outer),
                installed_outer_head_digest=_digest(outer),
                outer_commit_receipt_digest=_digest(generic),
                prior_registry_head_digest=_digest(prior_registry),
                installed_registry_head_digest=_digest(registry),
                prior_entry_head_digest=None,
                installed_entry_head_digest=None,
                installed_selector_version=context.selector_version,
                installed_selector_digest=_digest(selector),
                sibling_preservation_digest=_digest(tuple(sorted(entries.items()))),
            )
            receipt = ObserverAuthorizationClockRestartCommitReceipt(
                transition_fact_digest=_digest(fact),
                prior_outer_head_digest=_digest(prior_outer),
                installed_outer_head_digest=_digest(outer),
                prior_registry_head_digest=_digest(prior_registry),
                installed_registry_head_digest=_digest(registry),
                installed_selector_version=context.selector_version,
                installed_selector_digest=_digest(selector),
                outer_commit_receipt_digest=_digest(generic),
                registry_commit_receipt_digest=_digest(registry_receipt),
                affected_installed_keyed_head_digests=tuple(
                    _digest(item) for item in installed_ledgers
                ),
            )
            built["receipt"] = receipt
            return AtomicReceiptBundle(
                generic_commit_payload=generic,
                selector=selector,
                specialized_payloads=(registry_receipt, receipt),
            )

        candidate = AtomicCandidate(
            expected_snapshot_version=snapshot.snapshot_version,
            expected_state_digest=snapshot.state_digest,
            state=outer,
            objects=(
                fact,
                registry,
                outer,
                *installed_ledgers,
            ),
            transition_kind="OBSERVER_AUTHORIZATION_CLOCK_RESTART",
            operation_id=operation_id,
            deadline_intents=(),
            receipt_builder=receipt_builder,
            next_clock_incarnation=new_clock_incarnation,
        )
        self.store.commit_at_for_test(
            candidate,
            trusted_clock_sample=commit_time,
        )
        receipt = built["receipt"]
        _require(
            isinstance(receipt, ObserverAuthorizationClockRestartCommitReceipt),
            "server restart receipt factory did not run",
        )
        return receipt


@dataclass(frozen=True)
class TrustedDeliveryBoundaryGrantPreparationFact:
    operation_id: str
    full_boundary_key: TrustedDeliveryBoundaryGrantKey
    canonical_grant_digest: str
    boundary_installation_plan_digest: str
    stable_registry_key: ObserverGrantRegistryKey
    boundary_member: BoundaryMember
    deadline: BoundaryDeadline
    server_pending_outer_head_digest: str
    server_pending_registry_head_digest: str
    server_pending_keyed_head_digest: str
    server_selector_version: int
    server_outer_commit_receipt_digest: str
    server_registry_commit_receipt_digest: str
    prior_local_outer_head_digest: str
    prior_local_map_head_digest: str
    canonical_non_membership_proof_digest: str
    never_used_history_proof_digest: str
    predecessor_closure_receipt_digest: str | None
    predecessor_boundary_entry_digest: str | None
    deadline_intent_set_digest: str


@dataclass(frozen=True)
class TrustedDeliveryBoundaryGrantStateHead:
    full_boundary_key: TrustedDeliveryBoundaryGrantKey
    state_version: int
    prior_entry_head_digest: str | None
    descriptor_revision: int
    descriptor_digest: str
    boundary_member: BoundaryMember
    deadline: BoundaryDeadline
    phase: str
    preparation_fact_digest: str
    activation_fact_digest: str | None
    terminal_fact_digest: str | None
    quiescence_fact_digest: str | None
    installed_activation_set_receipt_digest: str | None
    installed_activation_entry_proof_digest: str | None
    pending_reservation_digests: tuple[str, ...]
    installed_release_counter_state_digest: str | None
    pre_release_commitment_digests: tuple[str, ...]
    released_outbox_commitment_digests: tuple[str, ...]
    active_drain_fact_digests: tuple[str, ...]
    terminal_disposition_digests: tuple[str, ...]
    canceled_reservation_tombstones: tuple[str, ...]
    deadline_intent_set_digest: str | None
    clock_restart_ancestry: tuple[str, ...]


BOUNDARY_PHASES = frozenset(
    {
        "PREPARED_BOUNDARY_GRANT",
        "LIVE_BOUNDARY_GRANT",
        "TERMINAL_BOUNDARY_GRANT",
        "TRANSPORT_QUIESCENT_BOUNDARY_GRANT",
    }
)


@dataclass(frozen=True)
class TrustedDeliveryBoundaryGrantMapHead:
    boundary_principal: str
    boundary_instance: str
    map_incarnation: str
    state_version: int
    prior_map_head_digest: str | None
    entries: tuple[tuple[str, str], ...]
    retired_key_tombstones: tuple[str, ...]
    transition_fact_digest: str | None


@dataclass(frozen=True)
class TrustedDeliveryReleaseStateHead:
    boundary_principal: str
    boundary_instance: str
    delivery_domain: str
    deadline_policy_id: str
    state_incarnation: str
    state_version: int
    prior_outer_head_digest: str | None
    security_state_digest: str
    current_security_key_id: str
    boundary_clock_incarnation: str
    grant_map_head_digest: str
    next_release_sequence: int
    next_output_slot: int
    next_attempt_sequence: int
    outbox_items: tuple[tuple[str, str], ...]
    drain_facts: tuple[tuple[str, str], ...]
    drain_dispositions: tuple[tuple[str, str], ...]
    used_release_identities: tuple[str, ...]
    consumed_read_decision_digests: tuple[str, ...]
    installed_release_counter_state_digests: tuple[tuple[str, str], ...]
    used_output_slots: tuple[int, ...]
    used_attempt_identities: tuple[str, ...]
    transition_fact_digest: str | None


@dataclass(frozen=True)
class InstalledTrustedDeliveryReleaseSelector:
    state_incarnation: str
    selector_version: int
    selected_head_digest: str
    generic_commit_receipt_digest: str


@dataclass(frozen=True)
class TrustedDeliveryReleaseStateCommitReceipt:
    transition_kind: str
    operation_id: str
    operation_commitment_digest: str
    prior_outer_head_digest: str | None
    installed_outer_head_digest: str
    installed_selector_version: int
    deadline_intent_set_digest: str | None
    deadline_conditions: tuple[CommitTimeDeadlineCondition, ...]


@dataclass(frozen=True)
class TrustedDeliveryBoundaryGrantMapCommitReceipt:
    transition_kind: str
    operation_id: str
    operation_commitment_digest: str
    prior_outer_head_digest: str | None
    installed_outer_head_digest: str
    prior_map_head_digest: str | None
    installed_map_head_digest: str
    prior_entry_head_digests: tuple[str, ...]
    installed_entry_head_digests: tuple[str, ...]
    installed_selector_version: int
    installed_selector_digest: str
    outer_commit_receipt_digest: str
    sibling_preservation_digest: str


@dataclass(frozen=True)
class TrustedDeliveryBoundaryGrantEnforcementReceipt:
    preparation_fact_digest: str
    canonical_grant_digest: str
    boundary_installation_plan_digest: str
    prior_outer_head_digest: str
    installed_outer_head_digest: str
    prior_map_head_digest: str
    installed_map_head_digest: str
    prior_entry_head_digest: str | None
    installed_entry_head_digest: str
    installed_selector_version: int
    installed_selector_digest: str
    outer_commit_receipt_digest: str
    map_commit_receipt_digest: str
    deadline_intent_set_digest: str
    deadline_conditions: tuple[CommitTimeDeadlineCondition, ...]
    signer_principal: str
    signer_key_id: str
    signer_security_state_digest: str


@dataclass(frozen=True)
class TrustedDeliveryBoundaryGrantActivationFact:
    operation_id: str
    full_boundary_key: TrustedDeliveryBoundaryGrantKey
    server_snapshot_persistence_root: str
    server_selector_version: int
    server_selector_digest: str
    server_activation_set_receipt_digest: str
    server_activation_entry_proof_digest: str
    prior_outer_head_digest: str
    prior_map_head_digest: str
    prior_entry_head_digest: str
    deadline: BoundaryDeadline
    security_currentness_digest: str
    deadline_intent_set_digest: str


@dataclass(frozen=True)
class TrustedDeliveryBoundaryGrantActivationReceipt:
    activation_fact_digest: str
    prior_outer_head_digest: str
    installed_outer_head_digest: str
    prior_map_head_digest: str
    installed_map_head_digest: str
    prior_entry_head_digest: str
    installed_entry_head_digest: str
    installed_selector_version: int
    installed_selector_digest: str
    outer_commit_receipt_digest: str
    map_commit_receipt_digest: str
    deadline_intent_set_digest: str
    deadline_conditions: tuple[CommitTimeDeadlineCondition, ...]
    signer_principal: str
    signer_key_id: str
    signer_security_state_digest: str


@dataclass(frozen=True)
class TrustedDeliveryReleaseReservation:
    operation_id: str
    full_boundary_key: TrustedDeliveryBoundaryGrantKey
    release_sequence: int
    output_slot: int
    payload_digest: str
    payload_length: int
    canonical_scope_digest: str
    boundary_scope_membership_digest: str
    read_authorization_decision_digest: str
    retained_authorization_cut: ExpectedObserverReadAuthorizationCut
    release_authority_recheck_digest: str
    release_recipient_context: SyntheticVerifiedReleaseRecipientContext
    expected_release_transport_context: tuple[str, str, str]
    qualified_deadline_mapping: QualifiedDecisionDeadlineMapping
    expected_deadline_mapping_state_cut: ExpectedQualifiedDeadlineMappingStateCut
    grant_currentness_evidence: SyntheticAuthenticatedGrantCurrentnessEvidence
    expected_grant_currentness_state_cut: ExpectedGrantCurrentnessStateCut
    release_cas: ObserverReadReleaseCAS
    validated_release_cas_receipt: SyntheticValidatedObserverReadReleaseCASReceipt
    requester_principal: str
    activation_receipt_digest: str
    deadline_intent_set_digest: str


@dataclass(frozen=True)
class TrustedDeliveryReleaseOutboxCommitment:
    operation_id: str
    reservation_digest: str
    validated_release_reservation_digest: str
    full_boundary_key: TrustedDeliveryBoundaryGrantKey
    stable_item_id: str
    idempotency_key: str
    attempt_namespace: str
    payload_digest: str
    payload_length: int
    output_slot: int
    canonical_scope_digest: str
    boundary_scope_membership_digest: str
    read_authorization_decision_digest: str
    release_authority_recheck_digest: str
    deadline_intent_set_digest: str


@dataclass(frozen=True)
class TrustedDeliveryReleaseReceipt:
    outbox_commitment_digest: str
    prior_outer_head_digest: str
    installed_outer_head_digest: str
    prior_map_head_digest: str
    installed_map_head_digest: str
    prior_entry_head_digest: str
    installed_entry_head_digest: str
    installed_selector_version: int
    installed_selector_digest: str
    outer_commit_receipt_digest: str
    map_commit_receipt_digest: str
    output_slot: int
    canonical_scope_digest: str
    boundary_scope_membership_digest: str
    read_authorization_decision_digest: str
    release_authority_recheck_digest: str
    enforcement_receipt_digest: str
    activation_receipt_digest: str
    deadline_intent_set_digest: str
    deadline_conditions: tuple[CommitTimeDeadlineCondition, ...]
    bridge_validated_release_cas_receipt_artifact_digest: str
    bridge_commit_receipt_artifact_digest: str
    bridge_prior_storage_state_head_digest: str
    bridge_installed_storage_state_head_digest: str


@dataclass(frozen=True)
class TrustedDeliveryReleaseOutbox:
    stable_item_id: str
    full_boundary_key: TrustedDeliveryBoundaryGrantKey
    outbox_commitment_digest: str
    release_receipt_digest: str
    idempotency_key: str
    attempt_namespace: str
    payload_digest: str
    payload_length: int
    complete_payload: bytes
    output_slot: int
    canonical_scope_digest: str
    boundary_scope_membership_digest: str
    read_authorization_decision_digest: str
    release_authority_recheck_digest: str
    committed_bridge_outbox_artifact: SyntheticCommittedObserverReadOutboxArtifact
    bridge_commit_receipt: SyntheticObserverReadOutboxCommitReceipt
    expected_bridge_commit_state_cut: ExpectedCommittedObserverReadOutboxStateCut


@dataclass(frozen=True)
class TrustedDeliveryExternalTransportDrainFact:
    operation_id: str
    stable_item_id: str
    full_boundary_key: TrustedDeliveryBoundaryGrantKey
    exact_outbox_item_digest: str
    idempotency_key: str
    actual_dispatch_payload: bytes
    dispatch_context: SyntheticAuthenticatedDispatchContext
    expected_dispatch_destination_cut: ExpectedDispatchDestinationCut
    dispatch_context_artifact_digest: str
    attempt_identity: str
    attempt_sequence: int
    canonical_scope_digest: str
    boundary_scope_membership_digest: str
    read_authorization_decision_digest: str
    release_authority_recheck_digest: str
    receiver_dedup_retry_proof_digest: str | None


@dataclass(frozen=True, slots=True)
class _SyntheticExternalTransportEnqueueRecord:
    """Coordinator-owned proof that exact bytes crossed the synthetic enqueue CAS."""

    attempt_identity: str
    drain_fact_digest: str
    persistence_root: str
    snapshot_version: int
    writer_epoch: int
    writer_exclusive_not_after: int
    transport_gate_epoch: int
    transport_gate_state_digest: str
    boundary_clock_incarnation: str
    enqueue_clock_sample: int
    payload_digest: str
    payload_length: int
    destination_cut_digest: str
    queue_sequence: int


@dataclass(frozen=True)
class TrustedDeliveryExternalTransportDisposition:
    drain_fact_digest: str
    dispatch_context_artifact_digest: str
    stable_item_id: str
    attempt_identity: str
    attempt_sequence: int
    outcome: str
    canonical_scope_digest: str
    boundary_scope_membership_digest: str
    read_authorization_decision_digest: str
    release_authority_recheck_digest: str
    authenticated_transport_evidence_digest: str | None
    no_resend_right: bool


@dataclass(frozen=True)
class SyntheticAuthenticatedTransportDispositionEvidence:
    """Fixture-authenticated evidence for one definitive transport outcome."""

    provenance_kind: str
    transport_authority_principal: str
    transport_authority_key_id: str
    transport_authority_incarnation: str
    outcome: str
    observation_clock_domain: str
    observation_clock_incarnation: str
    observed_at: int
    drain_fact_digest: str
    attempt_identity: str
    stable_outbox_item_id: str
    dispatch_context_artifact_digest: str
    destination_cut_digest: str
    endpoint_profile: str
    connection_instance: str
    replay_domain: str
    transport_gate_state_digest: str
    transport_gate_epoch: int
    recipient_principal: str
    recipient_instance: str
    semantic_evidence_digest: str
    fixture_authentication_tag: str


def transport_disposition_evidence_semantic_digest(
    evidence: SyntheticAuthenticatedTransportDispositionEvidence,
) -> str:
    _evidence_type_id, evidence_snapshot = _artifact_field_snapshot(evidence)
    return _semantic_digest(
        "ncp.b01.SyntheticAuthenticatedTransportDispositionEvidence@1",
        tuple(
            field_value
            for field_name, field_value in evidence_snapshot
            if field_name
            not in {"fixture_authentication_tag", "semantic_evidence_digest"}
        ),
    )


def _transport_disposition_evidence_fixture_tag(
    semantic_evidence_digest: Any,
) -> str:
    _require(
        _is_hex64(semantic_evidence_digest),
        "transport evidence semantic digest is not lowercase SHA-256",
    )
    return hmac.new(
        _TRANSPORT_EVIDENCE_SEAL_KEY,
        b"NCP-B01-SYNTHETIC-TRANSPORT-DISPOSITION-EVIDENCE-V1\x00"
        + semantic_evidence_digest.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def seal_transport_disposition_evidence(
    evidence: SyntheticAuthenticatedTransportDispositionEvidence,
) -> SyntheticAuthenticatedTransportDispositionEvidence:
    _require(
        type(evidence) is SyntheticAuthenticatedTransportDispositionEvidence,
        "transport disposition evidence type is not exact",
    )
    evidence = replace(
        evidence,
        semantic_evidence_digest=(
            transport_disposition_evidence_semantic_digest(evidence)
        ),
    )
    return replace(
        evidence,
        fixture_authentication_tag=(
            _transport_disposition_evidence_fixture_tag(
                evidence.semantic_evidence_digest
            )
        ),
    )


def _fixture_transport_disposition_evidence(
    *,
    fact: TrustedDeliveryExternalTransportDrainFact,
    outcome: str,
    observed_at: int,
) -> SyntheticAuthenticatedTransportDispositionEvidence:
    context = fact.dispatch_context
    return seal_transport_disposition_evidence(
        SyntheticAuthenticatedTransportDispositionEvidence(
            provenance_kind="SYNTHETIC_AUTHENTICATED_TRANSPORT_DISPOSITION",
            transport_authority_principal=TRANSPORT_EVIDENCE_PRINCIPAL,
            transport_authority_key_id=TRANSPORT_EVIDENCE_KEY_ID,
            transport_authority_incarnation=TRANSPORT_EVIDENCE_INCARNATION,
            outcome=outcome,
            observation_clock_domain="boundary-monotonic",
            observation_clock_incarnation=context.boundary_clock_incarnation,
            observed_at=observed_at,
            drain_fact_digest=_digest(fact),
            attempt_identity=fact.attempt_identity,
            stable_outbox_item_id=fact.stable_item_id,
            dispatch_context_artifact_digest=(fact.dispatch_context_artifact_digest),
            destination_cut_digest=context.destination_cut_digest,
            endpoint_profile=context.endpoint_profile,
            connection_instance=context.connection_instance,
            replay_domain=context.replay_domain,
            transport_gate_state_digest=context.transport_gate_state_digest,
            transport_gate_epoch=context.transport_gate_epoch,
            recipient_principal=context.recipient_principal,
            recipient_instance=context.recipient_instance,
            semantic_evidence_digest="",
            fixture_authentication_tag="",
        )
    )


def validate_transport_disposition_evidence(
    evidence: SyntheticAuthenticatedTransportDispositionEvidence,
    *,
    fact: TrustedDeliveryExternalTransportDrainFact,
    outcome: str,
    commit_time: int,
    commit_clock_incarnation: str,
) -> None:
    _require(
        type(evidence) is SyntheticAuthenticatedTransportDispositionEvidence,
        "definitive transport evidence type is not exact",
    )
    context = fact.dispatch_context
    _require(
        evidence.provenance_kind == "SYNTHETIC_AUTHENTICATED_TRANSPORT_DISPOSITION"
        and evidence.transport_authority_principal == TRANSPORT_EVIDENCE_PRINCIPAL
        and evidence.transport_authority_key_id == TRANSPORT_EVIDENCE_KEY_ID
        and evidence.transport_authority_incarnation == TRANSPORT_EVIDENCE_INCARNATION
        and evidence.outcome == outcome
        and outcome in {"DELIVERED", "REJECTED"}
        and evidence.observation_clock_domain == "boundary-monotonic"
        and evidence.observation_clock_incarnation
        == commit_clock_incarnation
        == context.boundary_clock_incarnation
        and _safe_int(evidence.observed_at)
        and context.verified_at <= evidence.observed_at <= commit_time
        and evidence.observed_at < context.exclusive_not_after
        and evidence.drain_fact_digest == _digest(fact)
        and evidence.attempt_identity == fact.attempt_identity
        and evidence.stable_outbox_item_id == fact.stable_item_id
        and evidence.dispatch_context_artifact_digest
        == fact.dispatch_context_artifact_digest
        and evidence.destination_cut_digest
        == context.destination_cut_digest
        == dispatch_destination_cut_digest(fact.expected_dispatch_destination_cut)
        and (
            evidence.endpoint_profile,
            evidence.connection_instance,
            evidence.replay_domain,
        )
        == (
            context.endpoint_profile,
            context.connection_instance,
            context.replay_domain,
        )
        and evidence.transport_gate_state_digest == context.transport_gate_state_digest
        and evidence.transport_gate_epoch == context.transport_gate_epoch
        and (
            evidence.recipient_principal,
            evidence.recipient_instance,
        )
        == (
            context.recipient_principal,
            context.recipient_instance,
        )
        and evidence.semantic_evidence_digest
        == transport_disposition_evidence_semantic_digest(evidence)
        and hmac.compare_digest(
            evidence.fixture_authentication_tag,
            _transport_disposition_evidence_fixture_tag(
                evidence.semantic_evidence_digest
            ),
        ),
        "definitive transport evidence is untrusted, stale, or substituted",
    )


@dataclass(frozen=True)
class SyntheticReceiverDeduplicationRetryProof:
    provenance_kind: str
    stable_outbox_item_id: str
    committed_outbox_artifact_digest: str
    transport_idempotency_key: str
    prior_attempt_identity: str
    prior_disposition_digest: str
    stable_destination_digest: str
    receiver_deduplication_state_digest: str
    delivery_outcome: str
    semantic_proof_digest: str
    fixture_authentication_tag: str


def receiver_deduplication_retry_semantic_digest(
    proof: SyntheticReceiverDeduplicationRetryProof,
) -> str:
    _proof_type_id, proof_snapshot = _artifact_field_snapshot(proof)
    return _semantic_digest(
        "ncp.b01.SyntheticReceiverDeduplicationRetryProof@1",
        tuple(
            field_value
            for field_name, field_value in proof_snapshot
            if field_name not in {"fixture_authentication_tag", "semantic_proof_digest"}
        ),
    )


def _receiver_deduplication_retry_fixture_tag(
    semantic_proof_digest: str,
) -> str:
    _require(
        _is_hex64(semantic_proof_digest),
        "retry proof semantic digest is not a lowercase SHA-256 digest",
    )
    return hmac.new(
        _READ_DECISION_SEAL_KEY,
        (
            b"NCP-B01-SYNTHETIC-RECEIVER-DEDUPLICATION-RETRY-PROOF-V1\x00"
            + semantic_proof_digest.encode("ascii")
        ),
        hashlib.sha256,
    ).hexdigest()


def seal_receiver_deduplication_retry_proof(
    proof: SyntheticReceiverDeduplicationRetryProof,
) -> SyntheticReceiverDeduplicationRetryProof:
    proof = replace(
        proof,
        semantic_proof_digest=(receiver_deduplication_retry_semantic_digest(proof)),
    )
    return replace(
        proof,
        fixture_authentication_tag=_receiver_deduplication_retry_fixture_tag(
            proof.semantic_proof_digest
        ),
    )


def validate_receiver_deduplication_retry_proof(
    proof: SyntheticReceiverDeduplicationRetryProof,
    *,
    outbox: TrustedDeliveryReleaseOutbox,
    prior_fact: TrustedDeliveryExternalTransportDrainFact,
    prior_disposition: TrustedDeliveryExternalTransportDisposition,
    expected_destination_cut: ExpectedDispatchDestinationCut,
) -> None:
    _require(
        type(proof) is SyntheticReceiverDeduplicationRetryProof,
        "receiver deduplication retry proof type is not exact",
    )
    for value, label in (
        (proof.stable_outbox_item_id, "retry proof stable item"),
        (proof.transport_idempotency_key, "retry proof transport idempotency"),
        (proof.prior_attempt_identity, "retry proof prior attempt"),
    ):
        _require(_is_uuid4(value), f"{label} is not a canonical UUIDv4")
    for value, label in (
        (
            proof.committed_outbox_artifact_digest,
            "retry proof committed outbox",
        ),
        (proof.prior_disposition_digest, "retry proof prior disposition"),
        (
            proof.stable_destination_digest,
            "retry proof stable destination",
        ),
        (
            proof.receiver_deduplication_state_digest,
            "retry proof receiver deduplication state",
        ),
        (proof.semantic_proof_digest, "retry proof semantic digest"),
        (proof.fixture_authentication_tag, "retry proof fixture tag"),
    ):
        _require(_is_hex64(value), f"{label} is not a lowercase SHA-256 digest")
    _require(
        proof.provenance_kind == "SYNTHETIC_AUTHENTICATED_RECEIVER_DEDUPLICATION_RETRY"
        and proof.delivery_outcome == "UNKNOWN_NO_SUCCESS_INFERRED"
        and prior_disposition.outcome == "AMBIGUOUS_AFTER_EXTERNAL_TRANSPORT"
        and not prior_disposition.no_resend_right
        and proof.stable_outbox_item_id
        == prior_fact.stable_item_id
        == prior_disposition.stable_item_id
        == outbox.stable_item_id
        and proof.committed_outbox_artifact_digest
        == committed_outbox_artifact_digest(outbox.committed_bridge_outbox_artifact)
        and proof.transport_idempotency_key
        == prior_fact.idempotency_key
        == outbox.idempotency_key
        and proof.prior_attempt_identity
        == prior_fact.attempt_identity
        == prior_disposition.attempt_identity
        and proof.prior_disposition_digest == _digest(prior_disposition)
        and proof.stable_destination_digest
        == dispatch_stable_destination_digest(
            prior_fact.expected_dispatch_destination_cut
        )
        == dispatch_stable_destination_digest(expected_destination_cut)
        and proof.semantic_proof_digest
        == receiver_deduplication_retry_semantic_digest(proof)
        and hmac.compare_digest(
            proof.fixture_authentication_tag,
            _receiver_deduplication_retry_fixture_tag(
                proof.semantic_proof_digest,
            ),
        ),
        "ambiguous retry lacks the exact stable bytes, destination, "
        "idempotency identity, unknown outcome, or receiver deduplication proof",
    )


@dataclass(frozen=True)
class TrustedDeliveryBoundaryTerminalTransitionFact:
    operation_id: str
    full_boundary_key: TrustedDeliveryBoundaryGrantKey
    cause: str
    server_terminal_receipt_digest: str | None
    renewal_fence_receipt_digest: str | None
    prior_outer_head_digest: str
    prior_map_head_digest: str
    prior_entry_head_digest: str
    deadline: BoundaryDeadline
    canceled_reservation_digests: tuple[str, ...]
    canceled_pre_release_commitment_digests: tuple[str, ...]
    retained_outbox_item_digests: tuple[str, ...]
    retained_active_drain_fact_digests: tuple[str, ...]
    deadline_intent_set_digest: str | None


@dataclass(frozen=True)
class TrustedDeliveryBoundaryBulkTerminalTransitionFact:
    operation_id: str
    bulk_cause: str
    complete_affected_key_digests: tuple[str, ...]
    terminal_subfact_digests: tuple[str, ...]
    prior_outer_head_digest: str
    prior_map_head_digest: str


@dataclass(frozen=True)
class TrustedDeliveryBoundaryTerminalInstallationReceipt:
    bulk_envelope_digest: str | None
    terminal_fact_digest: str
    full_boundary_key: TrustedDeliveryBoundaryGrantKey
    prior_outer_head_digest: str
    installed_outer_head_digest: str
    prior_map_head_digest: str
    installed_map_head_digest: str
    prior_entry_head_digest: str
    installed_entry_head_digest: str
    installed_selector_version: int
    installed_selector_digest: str
    outer_commit_receipt_digest: str
    map_commit_receipt_digest: str
    canceled_reservation_digests: tuple[str, ...]
    retained_outbox_item_digests: tuple[str, ...]
    retained_active_drain_fact_digests: tuple[str, ...]
    deadline_conditions: tuple[CommitTimeDeadlineCondition, ...]
    signer_principal: str
    signer_key_id: str
    signer_security_state_digest: str


@dataclass(frozen=True)
class TrustedDeliveryBoundaryTransportQuiescenceFact:
    operation_id: str
    full_boundary_key: TrustedDeliveryBoundaryGrantKey
    terminal_entry_head_digest: str
    terminal_receipt_digest: str
    canonical_retained_item_root: str
    retained_item_count: int
    disposition_digests: tuple[str, ...]
    no_retry_state_digest: str
    authenticated_no_pending_proof_digest: str


@dataclass(frozen=True)
class TrustedDeliveryBoundaryTransportQuiescenceReceipt:
    quiescence_fact_digest: str
    prior_outer_head_digest: str
    installed_outer_head_digest: str
    prior_map_head_digest: str
    installed_map_head_digest: str
    prior_entry_head_digest: str
    installed_entry_head_digest: str
    installed_selector_version: int
    installed_selector_digest: str
    outer_commit_receipt_digest: str
    map_commit_receipt_digest: str
    signer_principal: str
    signer_key_id: str
    signer_security_state_digest: str


@dataclass(frozen=True)
class TrustedDeliveryBoundaryClockRestartBridge:
    operation_id: str
    boundary_principal: str
    boundary_instance: str
    delivery_domain: str
    prior_clock_incarnation: str
    new_clock_incarnation: str
    prior_outer_head_digest: str
    prior_map_head_digest: str
    complete_affected_key_digests: tuple[str, ...]
    mapped_entry_deadlines: tuple[tuple[str, BoundaryDeadline, BoundaryDeadline], ...]
    restart_mapping_qualification_digest: str


@dataclass(frozen=True)
class TrustedDeliveryBoundaryClockRestartCommitReceipt:
    bridge_digest: str
    prior_outer_head_digest: str
    installed_outer_head_digest: str
    prior_map_head_digest: str
    installed_map_head_digest: str
    prior_entry_head_digests: tuple[str, ...]
    installed_entry_head_digests: tuple[str, ...]
    installed_selector_version: int
    installed_selector_digest: str
    outer_commit_receipt_digest: str
    map_commit_receipt_digest: str


BOUNDARY_TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "PREPARE_BOUNDARY_GRANT": (
        frozenset({"ABSENT"}),
        "PREPARED_BOUNDARY_GRANT",
    ),
    "ACTIVATE_PREPARED_BOUNDARY_GRANT": (
        frozenset({"PREPARED_BOUNDARY_GRANT"}),
        "LIVE_BOUNDARY_GRANT",
    ),
    "TERMINATE_BOUNDARY_GRANT": (
        frozenset({"PREPARED_BOUNDARY_GRANT", "LIVE_BOUNDARY_GRANT"}),
        "TERMINAL_BOUNDARY_GRANT",
    ),
    "MARK_BOUNDARY_GRANT_TRANSPORT_QUIESCENT": (
        frozenset({"TERMINAL_BOUNDARY_GRANT"}),
        "TRANSPORT_QUIESCENT_BOUNDARY_GRANT",
    ),
}


def _boundary_transition_guard(kind: str, prior: str, installed: str) -> None:
    rule = BOUNDARY_TRANSITIONS.get(kind)
    _require(rule is not None, "unknown boundary phase transition")
    _require(prior in rule[0], f"{kind} rejects prior phase {prior}")
    _require(installed == rule[1], f"{kind} installs wrong phase")


BOUNDARY_RECEIPT_SCHEMAS.update(
    {
        "RELEASE_STATE_GENESIS_FROM_UNINITIALIZED": (
            "TrustedDeliveryReleaseStateCommitReceipt",
            ("TrustedDeliveryBoundaryGrantMapCommitReceipt",),
        ),
        "PREPARE_BOUNDARY_GRANT": (
            "TrustedDeliveryReleaseStateCommitReceipt",
            (
                "TrustedDeliveryBoundaryGrantMapCommitReceipt",
                "TrustedDeliveryBoundaryGrantEnforcementReceipt",
            ),
        ),
        "ACTIVATE_PREPARED_BOUNDARY_GRANT": (
            "TrustedDeliveryReleaseStateCommitReceipt",
            (
                "TrustedDeliveryBoundaryGrantMapCommitReceipt",
                "TrustedDeliveryBoundaryGrantActivationReceipt",
            ),
        ),
        "CREATE_TRUSTED_DELIVERY_RELEASE_RESERVATION": (
            "TrustedDeliveryReleaseStateCommitReceipt",
            ("TrustedDeliveryBoundaryGrantMapCommitReceipt",),
        ),
        "COMMIT_TRUSTED_DELIVERY_RELEASE_OUTBOX": (
            "TrustedDeliveryReleaseStateCommitReceipt",
            (
                "TrustedDeliveryBoundaryGrantMapCommitReceipt",
                "TrustedDeliveryReleaseReceipt",
            ),
        ),
        "START_EXTERNAL_TRANSPORT_DRAIN": (
            "TrustedDeliveryReleaseStateCommitReceipt",
            ("TrustedDeliveryBoundaryGrantMapCommitReceipt",),
        ),
        "RESOLVE_EXTERNAL_TRANSPORT_DRAIN": (
            "TrustedDeliveryReleaseStateCommitReceipt",
            ("TrustedDeliveryBoundaryGrantMapCommitReceipt",),
        ),
        "TERMINATE_BOUNDARY_GRANT": (
            "TrustedDeliveryReleaseStateCommitReceipt",
            (
                "TrustedDeliveryBoundaryGrantMapCommitReceipt",
                "TrustedDeliveryBoundaryTerminalInstallationReceipt",
            ),
        ),
    }
)

CO_COMMITTED_OBJECT_SCHEMAS.update(
    {
        "COMMIT_TRUSTED_DELIVERY_RELEASE_OUTBOX": ("TrustedDeliveryReleaseOutbox",),
    }
)


@dataclass(frozen=True)
class BoundaryPreparationResult:
    fact: TrustedDeliveryBoundaryGrantPreparationFact
    enforcement_receipt: TrustedDeliveryBoundaryGrantEnforcementReceipt
    installed_entry: TrustedDeliveryBoundaryGrantStateHead


@dataclass(frozen=True)
class BoundaryActivationResult:
    fact: TrustedDeliveryBoundaryGrantActivationFact
    activation_receipt: TrustedDeliveryBoundaryGrantActivationReceipt
    installed_entry: TrustedDeliveryBoundaryGrantStateHead


@dataclass(frozen=True)
class BoundaryReleaseResult:
    pending_reservation: TrustedDeliveryReleaseReservation
    reservation: TrustedDeliveryReleaseReservation
    commitment: TrustedDeliveryReleaseOutboxCommitment
    release_receipt: TrustedDeliveryReleaseReceipt
    outbox_item: TrustedDeliveryReleaseOutbox


@dataclass(frozen=True)
class BoundaryTerminalResult:
    fact: TrustedDeliveryBoundaryTerminalTransitionFact
    receipt: TrustedDeliveryBoundaryTerminalInstallationReceipt
    installed_entry: TrustedDeliveryBoundaryGrantStateHead


def _validate_server_terminal_anchor(
    server: ObserverAuthorizationServer,
    result: ServerTerminalResult,
    *,
    expected_key: TrustedDeliveryBoundaryGrantKey,
) -> tuple[ImmutableAuthoritySnapshot, str]:
    _require(
        type(server) is ObserverAuthorizationServer
        and type(result) is ServerTerminalResult,
        "server terminal anchor types are not exact",
    )
    snapshot = server.store.snapshot
    _validate_atomic_snapshot(snapshot)
    objects = _tuple_map(snapshot.objects)
    signed = _tuple_map(snapshot.signed_bytes)
    receipt = result.terminal_receipt
    fact = result.transition_fact
    policy = result.reattachment_policy_result
    terminal_head = result.installed_terminal_head
    _require(
        type(receipt) is ObserverGrantTerminalTransitionReceipt
        and type(fact) is ObserverGrantTerminalTransitionFact
        and type(policy) is ObserverGrantReattachmentPolicyResult
        and type(terminal_head) is ObserverGrantLedgerHead,
        "server terminal result contains a substituted component type",
    )
    receipt_digest = _digest(receipt)
    policy_digest = _digest(policy)
    matching = tuple(
        transition
        for transition in snapshot.transitions
        if transition.transition_kind == "TERMINATE_GRANT"
        and transition.installed_state_digest == snapshot.state_digest
        and transition.specialized_receipt_digests[-2:]
        == (receipt_digest, policy_digest)
    )
    _require(
        len(matching) == 1
        and objects.get(receipt_digest) == receipt
        and objects.get(policy_digest) == policy
        and objects.get(receipt.transition_fact_digest) == fact
        and objects.get(receipt.installed_keyed_head_digest) == terminal_head
        and fact.full_boundary_key == expected_key
        and terminal_head.full_boundary_key == expected_key
        and terminal_head.terminal_transition_fact_digest == _digest(fact)
        and policy.terminal_transition_receipt_digest == receipt_digest
        and policy.installed_terminal_keyed_head_digest == _digest(terminal_head),
        "server terminal anchor is mixed, stale, or outside one selected transition",
    )
    transition = matching[0]
    for payload in (receipt, policy):
        _verify_signed_bytes(
            payload,
            signed.get(_digest(payload), b""),
            expected_principal=snapshot.authority_principal,
            expected_key_id=transition.signing_key_id,
            expected_security_state=transition.security_state_digest,
        )
    return snapshot, receipt_digest


def _validate_server_renewal_fence_anchor(
    server: ObserverAuthorizationServer,
    fence: ObserverGrantRenewalPredecessorFenceReceipt,
    *,
    expected_key: TrustedDeliveryBoundaryGrantKey,
) -> tuple[ImmutableAuthoritySnapshot, str]:
    _require(
        type(server) is ObserverAuthorizationServer
        and type(fence) is ObserverGrantRenewalPredecessorFenceReceipt,
        "server renewal-fence anchor types are not exact",
    )
    snapshot = server.store.snapshot
    _validate_atomic_snapshot(snapshot)
    objects = _tuple_map(snapshot.objects)
    signed = _tuple_map(snapshot.signed_bytes)
    fence_digest = _digest(fence)
    matching = tuple(
        transition
        for transition in snapshot.transitions
        if transition.transition_kind == "BEGIN_GRANT_RENEWAL"
        and transition.installed_state_digest == snapshot.state_digest
        and fence_digest in transition.specialized_receipt_digests
    )
    _require(
        len(matching) == 1
        and objects.get(fence_digest) == fence
        and fence.g0_full_boundary_key == expected_key,
        "server renewal fence is stale, foreign, or outside one selected transition",
    )
    transition = matching[0]
    _verify_signed_bytes(
        fence,
        signed.get(fence_digest, b""),
        expected_principal=snapshot.authority_principal,
        expected_key_id=transition.signing_key_id,
        expected_security_state=transition.security_state_digest,
    )
    return snapshot, fence_digest


class TrustedDeliveryBoundary:
    """One independent terminating boundary and its sole composite selector."""

    def __init__(self, member: BoundaryMember) -> None:
        self.member = member
        self.state_incarnation = _uuid_for(("boundary-state", member.identity))
        self.map_incarnation = _uuid_for(("boundary-map", member.identity))
        (
            self.store,
            self._persistence_recovery_authority,
        ) = AtomicAuthorityStore.enroll(
            store_id=f"trusted-delivery-boundary:{member.boundary_instance}",
            authority_principal=member.boundary_principal,
            authority_key_id=member.security_key_id,
            security_state_digest=member.security_state_digest,
            clock_incarnation=member.clock_mapping.boundary_clock_incarnation,
            writer_exclusive_not_after=10_000,
        )

    @property
    def head(self) -> TrustedDeliveryReleaseStateHead:
        state = self.store.snapshot.state
        _require(
            isinstance(state, TrustedDeliveryReleaseStateHead),
            "boundary is not initialized",
        )
        return state

    def grant_map(
        self,
        head: TrustedDeliveryReleaseStateHead | None = None,
    ) -> TrustedDeliveryBoundaryGrantMapHead:
        selected = head or self.head
        return self.store.object(
            selected.grant_map_head_digest,
            TrustedDeliveryBoundaryGrantMapHead,
        )

    def entry(
        self,
        key: TrustedDeliveryBoundaryGrantKey,
    ) -> TrustedDeliveryBoundaryGrantStateHead | None:
        entry_digest = _tuple_map(self.grant_map().entries).get(_digest(key))
        if entry_digest is None:
            return None
        return self.store.object(
            entry_digest,
            TrustedDeliveryBoundaryGrantStateHead,
        )

    def _deadline_intent(
        self,
        *,
        purpose: str,
        kind: str,
        deadline: int,
        transition_kind: str,
        operation_id: str,
    ) -> AuthorizationDeadlineConditionIntent:
        snapshot = self.store.snapshot
        return _intent(
            purpose,
            kind,
            snapshot.clock_incarnation,
            deadline,
            store_id=snapshot.store_id,
            authority_principal=snapshot.authority_principal,
            transition_kind=transition_kind,
            operation_id=operation_id,
            expected_prior_state_digest=snapshot.state_digest,
            expected_prior_selector_version=snapshot.snapshot_version,
            security_state_digest=snapshot.security_state_digest,
        )

    def _install(
        self,
        *,
        transition_kind: str,
        operation_id: str,
        prior_outer: TrustedDeliveryReleaseStateHead | None,
        installed_outer: TrustedDeliveryReleaseStateHead,
        installed_map: TrustedDeliveryBoundaryGrantMapHead,
        changed_entries: Sequence[
            tuple[
                TrustedDeliveryBoundaryGrantStateHead | None,
                TrustedDeliveryBoundaryGrantStateHead,
            ]
        ],
        objects: Sequence[Any],
        specialized_builder: Callable[
            [
                AtomicReceiptContext,
                TrustedDeliveryReleaseStateCommitReceipt,
                TrustedDeliveryBoundaryGrantMapCommitReceipt,
                InstalledTrustedDeliveryReleaseSelector,
            ],
            tuple[Any, ...] | tuple[tuple[Any, ...], tuple[Any, ...]],
        ],
        commit_time: int,
        deadline_intents: Sequence[AuthorizationDeadlineConditionIntent] = (),
        next_clock_incarnation: str | None = None,
        allocate_state_incarnation: str | None = None,
        fault_cut: str | None = None,
    ) -> AtomicTransitionRecord:
        snapshot = self.store.snapshot
        _require(snapshot.state == prior_outer, "boundary prior head is not current")
        prior_map = None if prior_outer is None else self.grant_map(prior_outer)
        _require(
            installed_outer.prior_outer_head_digest
            == (None if prior_outer is None else _digest(prior_outer)),
            "boundary outer ancestry mismatch",
        )
        _require(
            installed_outer.state_version
            == (1 if prior_outer is None else prior_outer.state_version + 1),
            "boundary outer version is not strict",
        )
        _require(
            installed_map.prior_map_head_digest
            == (None if prior_map is None else _digest(prior_map)),
            "boundary map ancestry mismatch",
        )
        _require(
            installed_map.state_version
            == (1 if prior_map is None else prior_map.state_version + 1),
            "boundary map version is not strict",
        )
        _require(
            installed_outer.grant_map_head_digest == _digest(installed_map),
            "boundary outer head does not bind installed map",
        )
        _require(
            installed_outer.boundary_principal == self.member.boundary_principal
            and installed_outer.boundary_instance == self.member.boundary_instance
            and installed_outer.delivery_domain == self.member.delivery_domain
            and installed_outer.deadline_policy_id == self.member.deadline_policy_id,
            "boundary outer identity drift",
        )
        prior_entries = {} if prior_map is None else _tuple_map(prior_map.entries)
        installed_entries = _tuple_map(installed_map.entries)
        changed_keys: set[str] = set()
        prior_entry_digests: list[str] = []
        installed_entry_digests: list[str] = []
        for prior_entry, installed_entry in changed_entries:
            key_digest = _digest(installed_entry.full_boundary_key)
            _require(key_digest not in changed_keys, "duplicate changed boundary key")
            changed_keys.add(key_digest)
            expected_prior_digest = (
                None if prior_entry is None else _digest(prior_entry)
            )
            _require(
                prior_entries.get(key_digest) == expected_prior_digest,
                "stale or fabricated boundary entry predecessor",
            )
            _require(
                installed_entry.prior_entry_head_digest == expected_prior_digest,
                "boundary entry ancestry mismatch",
            )
            _require(
                installed_entry.state_version
                == (1 if prior_entry is None else prior_entry.state_version + 1),
                "boundary entry version is not strict",
            )
            _require(
                installed_entries.get(key_digest) == _digest(installed_entry),
                "installed entry is not a map member",
            )
            prior_entry_digests.append(expected_prior_digest or "")
            installed_entry_digests.append(_digest(installed_entry))
        for key_digest, entry_digest in prior_entries.items():
            if key_digest not in changed_keys:
                _require(
                    installed_entries.get(key_digest) == entry_digest,
                    "unrelated boundary sibling changed",
                )
        expected_keys = set(prior_entries)
        expected_keys.update(
            _digest(installed_entry.full_boundary_key)
            for prior_entry, installed_entry in changed_entries
            if prior_entry is None
        )
        _require(
            set(installed_entries) == expected_keys,
            "boundary map added or removed an undeclared key",
        )
        _require(len(installed_entries) <= MAX_GRANTS, "boundary map capacity")
        intent_tuple = tuple(deadline_intents)

        def receipt_builder(context: AtomicReceiptContext) -> AtomicReceiptBundle:
            generic = TrustedDeliveryReleaseStateCommitReceipt(
                transition_kind=transition_kind,
                operation_id=context.operation_id,
                operation_commitment_digest=(context.operation_commitment_digest),
                prior_outer_head_digest=(
                    None if prior_outer is None else _digest(prior_outer)
                ),
                installed_outer_head_digest=_digest(installed_outer),
                installed_selector_version=context.selector_version,
                deadline_intent_set_digest=(
                    _intent_set_digest(context.deadline_intents)
                    if context.deadline_intents
                    else None
                ),
                deadline_conditions=context.deadline_conditions,
            )
            selector = InstalledTrustedDeliveryReleaseSelector(
                state_incarnation=installed_outer.state_incarnation,
                selector_version=context.selector_version,
                selected_head_digest=_digest(installed_outer),
                generic_commit_receipt_digest=_digest(generic),
            )
            map_receipt = TrustedDeliveryBoundaryGrantMapCommitReceipt(
                transition_kind=transition_kind,
                operation_id=context.operation_id,
                operation_commitment_digest=(context.operation_commitment_digest),
                prior_outer_head_digest=(
                    None if prior_outer is None else _digest(prior_outer)
                ),
                installed_outer_head_digest=_digest(installed_outer),
                prior_map_head_digest=(
                    None if prior_map is None else _digest(prior_map)
                ),
                installed_map_head_digest=_digest(installed_map),
                prior_entry_head_digests=tuple(prior_entry_digests),
                installed_entry_head_digests=tuple(installed_entry_digests),
                installed_selector_version=context.selector_version,
                installed_selector_digest=_digest(selector),
                outer_commit_receipt_digest=_digest(generic),
                sibling_preservation_digest=_semantic_digest(
                    "ncp.b01.BoundarySiblingPreservation@1",
                    tuple(
                        sorted(
                            (key, value)
                            for key, value in installed_entries.items()
                            if key not in changed_keys
                        )
                    ),
                ),
            )
            built = specialized_builder(
                context,
                generic,
                map_receipt,
                selector,
            )
            if (
                len(built) == 2
                and isinstance(built[0], tuple)
                and isinstance(built[1], tuple)
            ):
                specialized, co_objects = built
            else:
                specialized = built
                co_objects = ()
            return AtomicReceiptBundle(
                generic_commit_payload=generic,
                selector=selector,
                specialized_payloads=(map_receipt, *specialized),
                co_committed_objects=co_objects,
            )

        candidate = AtomicCandidate(
            expected_snapshot_version=snapshot.snapshot_version,
            expected_state_digest=snapshot.state_digest,
            state=installed_outer,
            objects=(
                *objects,
                installed_map,
                installed_outer,
                *(item[1] for item in changed_entries),
            ),
            transition_kind=transition_kind,
            operation_id=operation_id,
            deadline_intents=intent_tuple,
            receipt_builder=receipt_builder,
            next_clock_incarnation=next_clock_incarnation,
            allocate_state_incarnation=allocate_state_incarnation,
        )
        return self.store.commit_at_for_test(
            candidate,
            trusted_clock_sample=commit_time,
            fault_cut=fault_cut,
        )

    def genesis(
        self,
        *,
        commit_time: int,
        fault_cut: str | None = None,
    ) -> None:
        _require(self.store.snapshot.state is None, "boundary genesis already used")
        allocation = _parent_allocation_receipt(
            store_id=self.store.snapshot.store_id,
            state_incarnation=self.state_incarnation,
        )
        grant_map = TrustedDeliveryBoundaryGrantMapHead(
            boundary_principal=self.member.boundary_principal,
            boundary_instance=self.member.boundary_instance,
            map_incarnation=self.map_incarnation,
            state_version=1,
            prior_map_head_digest=None,
            entries=(),
            retired_key_tombstones=(),
            transition_fact_digest=_digest(allocation),
        )
        outer = TrustedDeliveryReleaseStateHead(
            boundary_principal=self.member.boundary_principal,
            boundary_instance=self.member.boundary_instance,
            delivery_domain=self.member.delivery_domain,
            deadline_policy_id=self.member.deadline_policy_id,
            state_incarnation=self.state_incarnation,
            state_version=1,
            prior_outer_head_digest=None,
            security_state_digest=self.member.security_state_digest,
            current_security_key_id=self.member.security_key_id,
            boundary_clock_incarnation=(
                self.member.clock_mapping.boundary_clock_incarnation
            ),
            grant_map_head_digest=_digest(grant_map),
            next_release_sequence=1,
            next_output_slot=1,
            next_attempt_sequence=1,
            outbox_items=(),
            drain_facts=(),
            drain_dispositions=(),
            used_release_identities=(),
            consumed_read_decision_digests=(),
            installed_release_counter_state_digests=(),
            used_output_slots=(),
            used_attempt_identities=(),
            transition_fact_digest=_digest(allocation),
        )
        self._install(
            transition_kind="RELEASE_STATE_GENESIS_FROM_UNINITIALIZED",
            operation_id=_uuid_for(("boundary-genesis", self.member.identity)),
            prior_outer=None,
            installed_outer=outer,
            installed_map=grant_map,
            changed_entries=(),
            objects=(allocation,),
            specialized_builder=(lambda _context, _generic, _map, _selector: ()),
            commit_time=commit_time,
            allocate_state_incarnation=self.state_incarnation,
            fault_cut=fault_cut,
        )

    def prepare(
        self,
        *,
        server: ObserverAuthorizationServer,
        plan: ObserverGrantBoundaryInstallationPlan,
        grant: ObserverGrant,
        predecessor_closure_receipt_digest: str | None,
        predecessor_key: TrustedDeliveryBoundaryGrantKey | None,
        commit_time: int,
    ) -> BoundaryPreparationResult:
        full_key = _full_key(plan, grant)
        _validate_plan_and_grant(plan, grant, full_key)
        _boundary_transition_guard(
            "PREPARE_BOUNDARY_GRANT",
            "ABSENT",
            "PREPARED_BOUNDARY_GRANT",
        )
        member_indexes = [
            index
            for index, member in enumerate(plan.boundary_members)
            if member.identity == self.member.identity
        ]
        _require(
            member_indexes == [member_indexes[0]] if member_indexes else False,
            "boundary is absent or duplicated in the plan",
        )
        member_index = member_indexes[0]
        deadline = plan.boundary_deadlines[member_index]
        _require(
            deadline.boundary_principal == self.member.boundary_principal
            and deadline.boundary_instance == self.member.boundary_instance
            and deadline.boundary_clock_incarnation
            == self.store.snapshot.clock_incarnation,
            "boundary deadline identity mismatch",
        )
        pending = server.entry(plan.stable_registry_key)
        _require(
            pending is not None
            and pending.phase == "PENDING_BOUNDARY_INSTALLATION"
            and pending.full_boundary_key == full_key,
            "server does not have this exact pending grant",
        )
        server_outer = server.head
        server_registry = server.registry()
        server_transition = server.store.snapshot.transitions[-1]
        _require(
            server_transition.installed_state_digest == _digest(server_outer),
            "server pending transition is not selected",
        )
        server_generic = server.store.object(
            server_transition.generic_commit_digest,
            ObserverAuthorizationStateCommitReceipt,
        )
        server_registry_receipt = server.store.object(
            server_transition.specialized_receipt_digests[0],
            ObserverGrantRegistryCommitReceipt,
        )
        prior_outer = self.head
        prior_map = self.grant_map()
        entries = _tuple_map(prior_map.entries)
        key_digest = _digest(full_key)
        _require(key_digest not in entries, "boundary full key is already present")
        _require(
            key_digest not in prior_map.retired_key_tombstones,
            "boundary full key was previously used",
        )
        predecessor_entry: TrustedDeliveryBoundaryGrantStateHead | None = None
        if predecessor_key is None:
            _require(
                predecessor_closure_receipt_digest is None
                and grant.issuance_sequence == 1,
                "initial preparation has predecessor evidence",
            )
        else:
            _require(
                predecessor_closure_receipt_digest is not None,
                "replacement preparation lacks distributed closure",
            )
            predecessor_entry = self.entry(predecessor_key)
            _require(
                predecessor_entry is not None
                and predecessor_entry.phase
                in {
                    "TERMINAL_BOUNDARY_GRANT",
                    "TRANSPORT_QUIESCENT_BOUNDARY_GRANT",
                },
                "renewal predecessor is not locally terminal or quiescent",
            )
            _require(
                predecessor_key.registry_key == full_key.registry_key
                and predecessor_key.issuance_sequence + 1 == full_key.issuance_sequence,
                "renewal predecessor relation is not exact",
            )
        non_membership = _semantic_digest(
            "ncp.b01.BoundaryGrantCanonicalNonMembership@1",
            (key_digest, _digest(prior_map), tuple(sorted(entries))),
        )
        never_used = _semantic_digest(
            "ncp.b01.BoundaryGrantNeverUsedHistory@1",
            (
                key_digest,
                prior_map.retired_key_tombstones,
                tuple(
                    transition.installed_state_digest
                    for transition in self.store.snapshot.transitions
                ),
            ),
        )
        operation_id = _uuid_for(
            (
                "boundary-prepare",
                self.member.identity,
                key_digest,
                _digest(prior_outer),
            )
        )
        intents = (
            self._deadline_intent(
                purpose=AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE,
                kind="BOUNDARY_GRANT_PREPARATION_CLOSE",
                deadline=deadline.boundary_prepare_close,
                transition_kind="PREPARE_BOUNDARY_GRANT",
                operation_id=operation_id,
            ),
            self._deadline_intent(
                purpose=AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE,
                kind="BOUNDARY_GRANT_RELEASE_NOT_AFTER",
                deadline=deadline.boundary_release_not_after,
                transition_kind="PREPARE_BOUNDARY_GRANT",
                operation_id=operation_id,
            ),
        )
        fact = TrustedDeliveryBoundaryGrantPreparationFact(
            operation_id=operation_id,
            full_boundary_key=full_key,
            canonical_grant_digest=_digest(grant),
            boundary_installation_plan_digest=_digest(plan),
            stable_registry_key=plan.stable_registry_key,
            boundary_member=self.member,
            deadline=deadline,
            server_pending_outer_head_digest=_digest(server_outer),
            server_pending_registry_head_digest=_digest(server_registry),
            server_pending_keyed_head_digest=_digest(pending),
            server_selector_version=server_transition.selector_version,
            server_outer_commit_receipt_digest=_digest(server_generic),
            server_registry_commit_receipt_digest=_digest(server_registry_receipt),
            prior_local_outer_head_digest=_digest(prior_outer),
            prior_local_map_head_digest=_digest(prior_map),
            canonical_non_membership_proof_digest=non_membership,
            never_used_history_proof_digest=never_used,
            predecessor_closure_receipt_digest=(predecessor_closure_receipt_digest),
            predecessor_boundary_entry_digest=(
                None if predecessor_entry is None else _digest(predecessor_entry)
            ),
            deadline_intent_set_digest=_intent_set_digest(intents),
        )
        entry = TrustedDeliveryBoundaryGrantStateHead(
            full_boundary_key=full_key,
            state_version=1,
            prior_entry_head_digest=None,
            descriptor_revision=plan.descriptor_revision,
            descriptor_digest=plan.descriptor_digest,
            boundary_member=self.member,
            deadline=deadline,
            phase="PREPARED_BOUNDARY_GRANT",
            preparation_fact_digest=_digest(fact),
            activation_fact_digest=None,
            terminal_fact_digest=None,
            quiescence_fact_digest=None,
            installed_activation_set_receipt_digest=None,
            installed_activation_entry_proof_digest=None,
            pending_reservation_digests=(),
            installed_release_counter_state_digest=None,
            pre_release_commitment_digests=(),
            released_outbox_commitment_digests=(),
            active_drain_fact_digests=(),
            terminal_disposition_digests=(),
            canceled_reservation_tombstones=(),
            deadline_intent_set_digest=_intent_set_digest(intents),
            clock_restart_ancestry=(),
        )
        entries[key_digest] = _digest(entry)
        installed_map = replace(
            prior_map,
            state_version=prior_map.state_version + 1,
            prior_map_head_digest=_digest(prior_map),
            entries=tuple(sorted(entries.items())),
            transition_fact_digest=_digest(fact),
        )
        installed_outer = replace(
            prior_outer,
            state_version=prior_outer.state_version + 1,
            prior_outer_head_digest=_digest(prior_outer),
            grant_map_head_digest=_digest(installed_map),
            transition_fact_digest=_digest(fact),
        )
        built: dict[str, Any] = {}

        def specialized_builder(
            context: AtomicReceiptContext,
            generic: TrustedDeliveryReleaseStateCommitReceipt,
            map_receipt: TrustedDeliveryBoundaryGrantMapCommitReceipt,
            selector: InstalledTrustedDeliveryReleaseSelector,
        ) -> tuple[Any, ...]:
            receipt = TrustedDeliveryBoundaryGrantEnforcementReceipt(
                preparation_fact_digest=_digest(fact),
                canonical_grant_digest=_digest(grant),
                boundary_installation_plan_digest=_digest(plan),
                prior_outer_head_digest=_digest(prior_outer),
                installed_outer_head_digest=_digest(installed_outer),
                prior_map_head_digest=_digest(prior_map),
                installed_map_head_digest=_digest(installed_map),
                prior_entry_head_digest=None,
                installed_entry_head_digest=_digest(entry),
                installed_selector_version=context.selector_version,
                installed_selector_digest=_digest(selector),
                outer_commit_receipt_digest=_digest(generic),
                map_commit_receipt_digest=_digest(map_receipt),
                deadline_intent_set_digest=_intent_set_digest(context.deadline_intents),
                deadline_conditions=context.deadline_conditions,
                signer_principal=context.authority_principal,
                signer_key_id=context.signing_key_id,
                signer_security_state_digest=context.security_state_digest,
            )
            built["receipt"] = receipt
            return (receipt,)

        self._install(
            transition_kind="PREPARE_BOUNDARY_GRANT",
            operation_id=operation_id,
            prior_outer=prior_outer,
            installed_outer=installed_outer,
            installed_map=installed_map,
            changed_entries=((None, entry),),
            objects=(
                plan,
                grant,
                full_key,
                fact,
                *intents,
                server.store.snapshot,
                server_outer,
                server_registry,
                pending,
                server_generic,
                server_registry_receipt,
            ),
            specialized_builder=specialized_builder,
            commit_time=commit_time,
            deadline_intents=intents,
        )
        receipt = built["receipt"]
        _require(
            isinstance(receipt, TrustedDeliveryBoundaryGrantEnforcementReceipt),
            "boundary enforcement receipt factory did not run",
        )
        return BoundaryPreparationResult(
            fact=fact,
            enforcement_receipt=receipt,
            installed_entry=entry,
        )

    def activate(
        self,
        *,
        preparation: BoundaryPreparationResult,
        server: ObserverAuthorizationServer,
        server_activation: ServerActivationResult,
        commit_time: int,
    ) -> BoundaryActivationResult:
        key = preparation.installed_entry.full_boundary_key
        prior_entry = self.entry(key)
        _require(
            prior_entry == preparation.installed_entry,
            "boundary activation predecessor is stale",
        )
        _boundary_transition_guard(
            "ACTIVATE_PREPARED_BOUNDARY_GRANT",
            prior_entry.phase,
            "LIVE_BOUNDARY_GRANT",
        )
        enforcement_digest = _digest(preparation.enforcement_receipt)
        _require(
            (self.member.identity, enforcement_digest)
            in server_activation.set_receipt.canonical_prepared_member_receipts,
            "server activation set omits this boundary enforcement receipt",
        )
        _require(
            server_activation.entry_proof.full_boundary_key == key
            and server_activation.set_receipt.installed_keyed_head_digest
            == _digest(server_activation.installed_ledger_head),
            "server activation evidence belongs to another grant",
        )
        server_snapshot = server.store.snapshot
        server_objects = _tuple_map(server_snapshot.objects)
        set_receipt_digest = _digest(server_activation.set_receipt)
        entry_proof_digest = _digest(server_activation.entry_proof)
        selected_server_transitions = tuple(
            transition
            for transition in server_snapshot.transitions
            if transition.transition_kind == "ACTIVATE_PENDING_GRANT"
            and transition.installed_state_digest == server_snapshot.state_digest
            and set_receipt_digest in transition.specialized_receipt_digests
            and entry_proof_digest in transition.specialized_receipt_digests
        )
        _require(
            len(selected_server_transitions) == 1
            and server_objects.get(set_receipt_digest) == server_activation.set_receipt
            and server_objects.get(entry_proof_digest) == server_activation.entry_proof
            and server_objects.get(
                server_activation.set_receipt.installed_keyed_head_digest
            )
            == server_activation.installed_ledger_head,
            "server activation components are mixed or not the selected state",
        )
        selected_server_transition = selected_server_transitions[0]
        for payload in (
            server_activation.set_receipt,
            server_activation.entry_proof,
        ):
            blob = server.store.recover_exact_signed_bytes(_digest(payload))
            _verify_signed_bytes(
                payload,
                blob,
                expected_principal=SERVER_PRINCIPAL,
                expected_key_id=SERVER_KEY_ID,
                expected_security_state=SECURITY_STATE_DIGEST,
            )
        prior_outer = self.head
        prior_map = self.grant_map()
        operation_id = _uuid_for(
            (
                "boundary-activate",
                self.member.identity,
                _digest(prior_entry),
                _digest(server_activation.set_receipt),
            )
        )
        intents = (
            self._deadline_intent(
                purpose=AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE,
                kind="BOUNDARY_GRANT_RELEASE_NOT_AFTER",
                deadline=prior_entry.deadline.boundary_release_not_after,
                transition_kind="ACTIVATE_PREPARED_BOUNDARY_GRANT",
                operation_id=operation_id,
            ),
        )
        fact = TrustedDeliveryBoundaryGrantActivationFact(
            operation_id=operation_id,
            full_boundary_key=key,
            server_snapshot_persistence_root=server.store.persistence_root,
            server_selector_version=selected_server_transition.selector_version,
            server_selector_digest=selected_server_transition.selector_digest,
            server_activation_set_receipt_digest=set_receipt_digest,
            server_activation_entry_proof_digest=entry_proof_digest,
            prior_outer_head_digest=_digest(prior_outer),
            prior_map_head_digest=_digest(prior_map),
            prior_entry_head_digest=_digest(prior_entry),
            deadline=prior_entry.deadline,
            security_currentness_digest=_semantic_digest(
                "ncp.b01.BoundarySecurityCurrentness@1",
                (
                    prior_outer.security_state_digest,
                    prior_outer.current_security_key_id,
                    self.member.security_state_digest,
                    self.member.security_key_id,
                ),
            ),
            deadline_intent_set_digest=_intent_set_digest(intents),
        )
        live = replace(
            prior_entry,
            state_version=prior_entry.state_version + 1,
            prior_entry_head_digest=_digest(prior_entry),
            phase="LIVE_BOUNDARY_GRANT",
            activation_fact_digest=_digest(fact),
            installed_activation_set_receipt_digest=_digest(
                server_activation.set_receipt
            ),
            installed_activation_entry_proof_digest=_digest(
                server_activation.entry_proof
            ),
            deadline_intent_set_digest=_intent_set_digest(intents),
        )
        entries = _tuple_map(prior_map.entries)
        entries[_digest(key)] = _digest(live)
        installed_map = replace(
            prior_map,
            state_version=prior_map.state_version + 1,
            prior_map_head_digest=_digest(prior_map),
            entries=tuple(sorted(entries.items())),
            transition_fact_digest=_digest(fact),
        )
        installed_outer = replace(
            prior_outer,
            state_version=prior_outer.state_version + 1,
            prior_outer_head_digest=_digest(prior_outer),
            grant_map_head_digest=_digest(installed_map),
            transition_fact_digest=_digest(fact),
        )
        built: dict[str, Any] = {}

        def specialized_builder(
            context: AtomicReceiptContext,
            generic: TrustedDeliveryReleaseStateCommitReceipt,
            map_receipt: TrustedDeliveryBoundaryGrantMapCommitReceipt,
            selector: InstalledTrustedDeliveryReleaseSelector,
        ) -> tuple[Any, ...]:
            receipt = TrustedDeliveryBoundaryGrantActivationReceipt(
                activation_fact_digest=_digest(fact),
                prior_outer_head_digest=_digest(prior_outer),
                installed_outer_head_digest=_digest(installed_outer),
                prior_map_head_digest=_digest(prior_map),
                installed_map_head_digest=_digest(installed_map),
                prior_entry_head_digest=_digest(prior_entry),
                installed_entry_head_digest=_digest(live),
                installed_selector_version=context.selector_version,
                installed_selector_digest=_digest(selector),
                outer_commit_receipt_digest=_digest(generic),
                map_commit_receipt_digest=_digest(map_receipt),
                deadline_intent_set_digest=_intent_set_digest(context.deadline_intents),
                deadline_conditions=context.deadline_conditions,
                signer_principal=context.authority_principal,
                signer_key_id=context.signing_key_id,
                signer_security_state_digest=context.security_state_digest,
            )
            built["receipt"] = receipt
            return (receipt,)

        self._install(
            transition_kind="ACTIVATE_PREPARED_BOUNDARY_GRANT",
            operation_id=operation_id,
            prior_outer=prior_outer,
            installed_outer=installed_outer,
            installed_map=installed_map,
            changed_entries=((prior_entry, live),),
            objects=(
                fact,
                *intents,
                server.store.snapshot,
                server_activation.set_receipt,
                server_activation.entry_proof,
            ),
            specialized_builder=specialized_builder,
            commit_time=commit_time,
            deadline_intents=intents,
        )
        receipt = built["receipt"]
        _require(
            isinstance(receipt, TrustedDeliveryBoundaryGrantActivationReceipt),
            "boundary activation receipt factory did not run",
        )
        return BoundaryActivationResult(
            fact=fact,
            activation_receipt=receipt,
            installed_entry=live,
        )

    def create_reservation(
        self,
        *,
        activation: BoundaryActivationResult,
        payload: bytes,
        read_scope: CanonicalObserverReadScope,
        boundary_membership: ObserverBoundaryReadScopeMembership,
        read_authorization_decision: SealedObserverReadAuthorizationDecision,
        retained_authorization_cut: ExpectedObserverReadAuthorizationCut,
        release_recipient_context: SyntheticVerifiedReleaseRecipientContext,
        expected_release_transport_context: tuple[str, str, str],
        expected_release_context_artifact_digest: str,
        release_idempotency_key: str,
        commit_time: int,
    ) -> TrustedDeliveryReleaseReservation:
        _require(
            type(payload) is bytes and 0 < len(payload) <= MAX_CANONICAL_STRING_CHARS,
            "release payload is empty, subclassed, or above the bounded result size",
        )
        prior_entry = self.entry(activation.installed_entry.full_boundary_key)
        _require(
            prior_entry is not None
            and prior_entry.phase == "LIVE_BOUNDARY_GRANT"
            and prior_entry.activation_fact_digest
            == activation.installed_entry.activation_fact_digest,
            "only the exact current LIVE boundary lineage can reserve",
        )
        if prior_entry.pending_reservation_digests:
            _require(
                len(prior_entry.pending_reservation_digests) == 1,
                "release intent fence is not exclusive",
            )
            existing = self.store.object(
                prior_entry.pending_reservation_digests[0],
                TrustedDeliveryReleaseReservation,
            )
            _require(
                existing.payload_digest == hashlib.sha256(payload).hexdigest()
                and existing.payload_length == len(payload)
                and existing.canonical_scope_digest == read_scope.scope_digest
                and existing.boundary_scope_membership_digest
                == boundary_membership.membership_digest
                and existing.read_authorization_decision_digest
                == _digest(read_authorization_decision)
                and existing.retained_authorization_cut == retained_authorization_cut
                and existing.release_recipient_context == release_recipient_context
                and existing.expected_release_transport_context
                == expected_release_transport_context
                and release_recipient_artifact_digest(
                    existing.release_recipient_context
                )
                == expected_release_context_artifact_digest
                and existing.release_cas.release_idempotency_key
                == release_idempotency_key
                and existing.activation_receipt_digest
                == _digest(activation.activation_receipt),
                "a different request conflicts with the exclusive release intent fence",
            )
            return existing
        _require(
            prior_entry == activation.installed_entry,
            "first release intent predecessor is stale",
        )
        preparation_fact = self.store.object(
            prior_entry.preparation_fact_digest,
            TrustedDeliveryBoundaryGrantPreparationFact,
        )
        plan = self.store.object(
            preparation_fact.boundary_installation_plan_digest,
            ObserverGrantBoundaryInstallationPlan,
        )
        try:
            validate_read_decision(
                read_authorization_decision,
                scope=read_scope,
                membership=boundary_membership,
                expected_boundary_identity=(
                    self.member.boundary_principal,
                    self.member.boundary_instance,
                    self.member.deadline_policy_id,
                ),
                expected_observer_identity=(
                    prior_entry.full_boundary_key.registry_key.requester_principal,
                    release_recipient_context.recipient_instance,
                ),
                expected_authorization_audience=read_scope.authorization_audience,
                expected_authorization_cut=retained_authorization_cut,
                expected_issuer_identity=(
                    SERVER_PRINCIPAL,
                    SERVER_KEY_ID,
                    SERVER_STATE_INCARNATION,
                ),
                fixture_key=_READ_DECISION_SEAL_KEY,
            )
        except BridgeValidationError as exc:
            raise ProbeError("release read decision failed sealed replay") from exc
        try:
            validate_release_recipient_context(
                release_recipient_context,
                membership=boundary_membership,
                expected_recipient_identity=(
                    prior_entry.full_boundary_key.registry_key.requester_principal,
                    release_recipient_context.recipient_instance,
                ),
                expected_transport_context=expected_release_transport_context,
                expected_local_security_state=(
                    self.member.security_state_digest,
                    plan.security_epoch,
                    plan.revocation_epoch,
                ),
                expected_boundary_clock_incarnation=(
                    self.member.clock_mapping.boundary_clock_incarnation
                ),
                expected_context_artifact_digest=(
                    expected_release_context_artifact_digest
                ),
                checked_at=commit_time,
                fixture_key=_READ_DECISION_SEAL_KEY,
            )
        except BridgeValidationError as exc:
            raise ProbeError("release recipient context is invalid") from exc
        _require(
            read_scope == self.member.read_scope
            and boundary_membership == self.member.scope_membership
            and read_scope.scope_digest in plan.exact_scope_digests
            and read_authorization_decision.full_boundary_key_digest
            == _digest(prior_entry.full_boundary_key)
            and read_authorization_decision.grant_digest
            == prior_entry.full_boundary_key.canonical_grant_digest
            and read_authorization_decision.observer_principal
            == prior_entry.full_boundary_key.registry_key.requester_principal
            and read_authorization_decision.security_state_digest
            == plan.security_state_digest
            and read_authorization_decision.security_epoch == plan.security_epoch
            and read_authorization_decision.revocation_epoch == plan.revocation_epoch
            and read_authorization_decision.coordinator_clock_incarnation
            == plan.coordinator_clock_incarnation
            and read_authorization_decision.maximum_release_count == 1,
            "release decision/scope/member is not the exact current grant authority",
        )
        prior_outer = self.head
        # This digest is the probe's typed canonical artifact identity. The
        # decision's semantic digest remains a distinct sealed field.
        decision_artifact_digest = _digest(read_authorization_decision)
        _require(
            decision_artifact_digest not in prior_outer.consumed_read_decision_digests,
            "single-release read decision was already consumed",
        )
        prior_map = self.grant_map()
        prior_release_count = prior_outer.consumed_read_decision_digests.count(
            decision_artifact_digest
        )
        _require(
            prior_release_count < read_authorization_decision.maximum_release_count,
            "read decision release quota is exhausted",
        )
        _require(
            prior_outer.next_release_sequence <= MAX_SAFE_INTEGER
            and prior_outer.next_output_slot <= MAX_SAFE_INTEGER,
            "release allocator exhausted",
        )
        release_identity = _uuid_for(
            (
                "release",
                self.member.identity,
                release_idempotency_key,
                prior_outer.next_release_sequence,
            )
        )
        _require(
            release_identity not in prior_outer.used_release_identities,
            "release identity reused",
        )
        _require(
            prior_outer.next_output_slot not in prior_outer.used_output_slots,
            "output slot reused",
        )
        operation_id = _uuid_for(
            (
                "reserve",
                release_identity,
                _digest(prior_entry),
                hashlib.sha256(payload).hexdigest(),
            )
        )
        mapped_decision_not_after = _map_lower(
            self.member.clock_mapping,
            read_authorization_decision.exclusive_not_after,
        )
        qualified_deadline_mapping = seal_qualified_deadline_mapping(
            QualifiedDecisionDeadlineMapping(
                provenance_kind=("SYNTHETIC_AUTHENTICATED_CONSERVATIVE_CLOCK_MAPPING"),
                decision_artifact_digest=read_decision_artifact_digest(
                    read_authorization_decision
                ),
                source_clock_incarnation=(
                    self.member.clock_mapping.coordinator_clock_incarnation
                ),
                source_exclusive_not_after=(
                    read_authorization_decision.exclusive_not_after
                ),
                boundary_clock_incarnation=(
                    self.member.clock_mapping.boundary_clock_incarnation
                ),
                coordinator_reference=(self.member.clock_mapping.coordinator_reference),
                boundary_reference_lower=(
                    self.member.clock_mapping.boundary_reference_lower
                ),
                source_applicability_start=(
                    self.member.clock_mapping.source_applicability_start
                ),
                source_applicability_end=(
                    self.member.clock_mapping.source_applicability_end
                ),
                target_applicability_start=(
                    self.member.clock_mapping.target_applicability_start
                ),
                target_applicability_end=(
                    self.member.clock_mapping.target_applicability_end
                ),
                minimum_rate_numerator=(
                    self.member.clock_mapping.minimum_rate_numerator
                ),
                minimum_rate_denominator=(
                    self.member.clock_mapping.minimum_rate_denominator
                ),
                rounding_rule="LOWER_FLOOR",
                correlation_authority=(self.member.clock_mapping.correlation_authority),
                qualification_digest=(self.member.clock_mapping.qualification_digest),
                source_receipt_digest=(self.member.clock_mapping.source_receipt_digest),
                source_receipt_authority=(
                    self.member.clock_mapping.source_receipt_authority
                ),
                source_receipt_current=(
                    self.member.clock_mapping.source_receipt_current
                ),
                mapping_policy_artifact_digest=_digest(self.member.clock_mapping),
                security_state_digest=self.member.security_state_digest,
                security_epoch=plan.security_epoch,
                revocation_epoch=plan.revocation_epoch,
                mapped_exclusive_not_after=mapped_decision_not_after,
                semantic_mapping_digest="",
                fixture_authentication_tag="",
            ),
            fixture_key=_READ_DECISION_SEAL_KEY,
        )
        expected_deadline_mapping_state_cut = ExpectedQualifiedDeadlineMappingStateCut(
            decision_artifact_digest=read_decision_artifact_digest(
                read_authorization_decision
            ),
            source_clock_incarnation=(
                self.member.clock_mapping.coordinator_clock_incarnation
            ),
            source_exclusive_not_after=(
                read_authorization_decision.exclusive_not_after
            ),
            boundary_clock_incarnation=(
                self.member.clock_mapping.boundary_clock_incarnation
            ),
            coordinator_reference=(self.member.clock_mapping.coordinator_reference),
            boundary_reference_lower=(
                self.member.clock_mapping.boundary_reference_lower
            ),
            source_applicability_start=(
                self.member.clock_mapping.source_applicability_start
            ),
            source_applicability_end=(
                self.member.clock_mapping.source_applicability_end
            ),
            target_applicability_start=(
                self.member.clock_mapping.target_applicability_start
            ),
            target_applicability_end=(
                self.member.clock_mapping.target_applicability_end
            ),
            minimum_rate_numerator=(self.member.clock_mapping.minimum_rate_numerator),
            minimum_rate_denominator=(
                self.member.clock_mapping.minimum_rate_denominator
            ),
            rounding_rule="LOWER_FLOOR",
            correlation_authority=(self.member.clock_mapping.correlation_authority),
            qualification_digest=(self.member.clock_mapping.qualification_digest),
            source_receipt_digest=(self.member.clock_mapping.source_receipt_digest),
            source_receipt_authority=(
                self.member.clock_mapping.source_receipt_authority
            ),
            source_receipt_current=(self.member.clock_mapping.source_receipt_current),
            mapping_policy_artifact_digest=_digest(self.member.clock_mapping),
            security_state_digest=self.member.security_state_digest,
            security_epoch=plan.security_epoch,
            revocation_epoch=plan.revocation_epoch,
            mapped_exclusive_not_after=mapped_decision_not_after,
        )
        grant_currentness_evidence = seal_grant_currentness_evidence(
            SyntheticAuthenticatedGrantCurrentnessEvidence(
                provenance_kind=("SYNTHETIC_AUTHENTICATED_BOUNDARY_GRANT_CURRENTNESS"),
                boundary_principal=self.member.boundary_principal,
                boundary_instance=self.member.boundary_instance,
                boundary_clock_incarnation=(
                    self.member.clock_mapping.boundary_clock_incarnation
                ),
                observer_principal=(
                    prior_entry.full_boundary_key.registry_key.requester_principal
                ),
                observer_instance=release_recipient_context.recipient_instance,
                canonical_scope_digest=read_scope.scope_digest,
                boundary_scope_membership_digest=(
                    boundary_membership.membership_digest
                ),
                read_decision_artifact_digest=(
                    read_decision_artifact_digest(read_authorization_decision)
                ),
                capability_digest=read_authorization_decision.capability_digest,
                grant_digest=read_authorization_decision.grant_digest,
                grant_currentness_receipt_digest=_digest(activation.activation_receipt),
                boundary_state_head_digest=_digest(prior_outer),
                grant_entry_head_digest=_digest(prior_entry),
                release_counter_state_digest="",
                state_version=prior_outer.state_version,
                prior_release_count=prior_release_count,
                local_grant_exclusive_not_after=(
                    prior_entry.deadline.boundary_release_not_after
                ),
                verified_at=commit_time,
                exclusive_not_after=(prior_entry.deadline.boundary_release_not_after),
                security_state_digest=self.member.security_state_digest,
                security_epoch=plan.security_epoch,
                revocation_epoch=plan.revocation_epoch,
                current=True,
                semantic_evidence_digest="",
                fixture_authentication_tag="",
            ),
            fixture_key=_READ_DECISION_SEAL_KEY,
        )
        expected_grant_currentness_state_cut = ExpectedGrantCurrentnessStateCut(
            boundary_state_head_digest=_digest(prior_outer),
            grant_entry_head_digest=_digest(prior_entry),
            state_version=prior_outer.state_version,
            prior_release_count=prior_release_count,
            grant_currentness_receipt_digest=_digest(activation.activation_receipt),
            local_grant_exclusive_not_after=(
                prior_entry.deadline.boundary_release_not_after
            ),
            evidence_artifact_digest=grant_currentness_artifact_digest(
                grant_currentness_evidence
            ),
        )
        release_ordinal = prior_release_count + 1
        release_cas = seal_release_cas(
            ObserverReadReleaseCAS(
                observer_principal=(
                    prior_entry.full_boundary_key.registry_key.requester_principal
                ),
                observer_instance=release_recipient_context.recipient_instance,
                source_session_kind=read_scope.source_session_kind,
                logical_session_id=read_scope.logical_session_id,
                source_generation=read_scope.source_generation,
                canonical_scope_digest=read_scope.scope_digest,
                boundary_scope_membership_digest=(
                    boundary_membership.membership_digest
                ),
                caller_operation_id=(read_authorization_decision.caller_operation_id),
                caller_request_digest=(
                    read_authorization_decision.caller_request_digest
                ),
                release_idempotency_key=release_idempotency_key,
                authorization_ingress_artifact_digest=(
                    authorization_ingress_artifact_digest(
                        read_authorization_decision.authorization_ingress_context
                    )
                ),
                release_recipient_context_artifact_digest=(
                    release_recipient_artifact_digest(release_recipient_context)
                ),
                read_decision_artifact_digest=read_decision_artifact_digest(
                    read_authorization_decision
                ),
                capability_digest=read_authorization_decision.capability_digest,
                grant_digest=read_authorization_decision.grant_digest,
                grant_currentness_evidence_artifact_digest=(
                    grant_currentness_artifact_digest(grant_currentness_evidence)
                ),
                boundary_clock_incarnation=(
                    self.member.clock_mapping.boundary_clock_incarnation
                ),
                prior_release_count=prior_release_count,
                release_ordinal=release_ordinal,
                prior_release_counter_state_digest=(
                    grant_currentness_evidence.release_counter_state_digest
                ),
                next_release_counter_state_digest=(
                    next_grant_release_counter_state_digest(
                        evidence=grant_currentness_evidence,
                        release_idempotency_key=release_idempotency_key,
                        release_ordinal=release_ordinal,
                    )
                ),
                local_grant_not_after=(prior_entry.deadline.boundary_release_not_after),
                grant_currentness_not_after=(
                    grant_currentness_evidence.exclusive_not_after
                ),
                qualified_deadline_mapping_artifact_digest=(
                    qualified_deadline_mapping_artifact_digest(
                        qualified_deadline_mapping
                    )
                ),
                mapped_decision_not_after=mapped_decision_not_after,
                local_release_context_not_after=(
                    release_recipient_context.exclusive_not_after
                ),
                effective_release_not_after=min(
                    prior_entry.deadline.boundary_release_not_after,
                    grant_currentness_evidence.exclusive_not_after,
                    mapped_decision_not_after,
                    release_recipient_context.exclusive_not_after,
                ),
                cas_digest="",
            )
        )
        try:
            validated_release_cas_receipt = issue_validated_release_cas_receipt(
                release_cas,
                validation_event_id=_uuid_for(
                    ("full-release-cas-validation", operation_id)
                ),
                validator_identity=(
                    self.member.boundary_principal,
                    self.member.boundary_instance,
                ),
                scope=read_scope,
                membership=boundary_membership,
                decision=read_authorization_decision,
                release_context=release_recipient_context,
                qualified_deadline_mapping=qualified_deadline_mapping,
                grant_currentness_evidence=grant_currentness_evidence,
                expected_observer_identity=(
                    prior_entry.full_boundary_key.registry_key.requester_principal,
                    release_recipient_context.recipient_instance,
                ),
                expected_boundary_identity=(
                    self.member.boundary_principal,
                    self.member.boundary_instance,
                    self.member.deadline_policy_id,
                ),
                expected_authorization_audience=(read_scope.authorization_audience),
                expected_authorization_cut=retained_authorization_cut,
                expected_issuer_identity=(
                    SERVER_PRINCIPAL,
                    SERVER_KEY_ID,
                    SERVER_STATE_INCARNATION,
                ),
                expected_release_recipient_identity=(
                    prior_entry.full_boundary_key.registry_key.requester_principal,
                    release_recipient_context.recipient_instance,
                ),
                expected_release_transport_context=(expected_release_transport_context),
                expected_local_security_state=(
                    self.member.security_state_digest,
                    plan.security_epoch,
                    plan.revocation_epoch,
                ),
                expected_release_context_artifact_digest=(
                    expected_release_context_artifact_digest
                ),
                expected_grant_currentness_state_cut=(
                    expected_grant_currentness_state_cut
                ),
                expected_deadline_mapping_state_cut=(
                    expected_deadline_mapping_state_cut
                ),
                release_idempotency_key=release_idempotency_key,
                expected_boundary_clock_incarnation=(
                    self.member.clock_mapping.boundary_clock_incarnation
                ),
                expected_mapping_policy_artifact_digest=_digest(
                    self.member.clock_mapping
                ),
                checked_at=commit_time,
                fixture_key=_READ_DECISION_SEAL_KEY,
            )
        except BridgeValidationError as exc:
            raise ProbeError("release CAS validation failed closed") from exc
        intents = (
            self._deadline_intent(
                purpose=AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE,
                kind="BOUNDARY_GRANT_RELEASE_NOT_AFTER",
                deadline=release_cas.effective_release_not_after,
                transition_kind=("CREATE_TRUSTED_DELIVERY_RELEASE_RESERVATION"),
                operation_id=operation_id,
            ),
        )
        release_authority_recheck_digest = _semantic_digest(
            "ncp.b01.TrustedDeliveryReleaseAuthorityRecheck@1",
            (
                _digest(read_authorization_decision),
                read_scope.scope_digest,
                boundary_membership.membership_digest,
                _digest(prior_entry),
                _digest(activation.activation_receipt),
                commit_time,
                operation_id,
            ),
        )
        reservation = TrustedDeliveryReleaseReservation(
            operation_id=operation_id,
            full_boundary_key=prior_entry.full_boundary_key,
            release_sequence=prior_outer.next_release_sequence,
            output_slot=prior_outer.next_output_slot,
            payload_digest=hashlib.sha256(payload).hexdigest(),
            payload_length=len(payload),
            canonical_scope_digest=read_scope.scope_digest,
            boundary_scope_membership_digest=boundary_membership.membership_digest,
            read_authorization_decision_digest=decision_artifact_digest,
            retained_authorization_cut=retained_authorization_cut,
            release_authority_recheck_digest=release_authority_recheck_digest,
            release_recipient_context=release_recipient_context,
            expected_release_transport_context=(expected_release_transport_context),
            qualified_deadline_mapping=qualified_deadline_mapping,
            expected_deadline_mapping_state_cut=(expected_deadline_mapping_state_cut),
            grant_currentness_evidence=grant_currentness_evidence,
            expected_grant_currentness_state_cut=(expected_grant_currentness_state_cut),
            release_cas=release_cas,
            validated_release_cas_receipt=validated_release_cas_receipt,
            requester_principal=(
                prior_entry.full_boundary_key.registry_key.requester_principal
            ),
            activation_receipt_digest=_digest(activation.activation_receipt),
            deadline_intent_set_digest=_intent_set_digest(intents),
        )
        reservation_digest = _digest(reservation)
        _require(
            not prior_entry.pending_reservation_digests,
            "release reservation fence is not exclusive",
        )
        installed_entry = replace(
            prior_entry,
            state_version=prior_entry.state_version + 1,
            prior_entry_head_digest=_digest(prior_entry),
            pending_reservation_digests=(reservation_digest,),
            deadline_intent_set_digest=_intent_set_digest(intents),
        )
        entries = _tuple_map(prior_map.entries)
        entries[_digest(prior_entry.full_boundary_key)] = _digest(installed_entry)
        installed_map = replace(
            prior_map,
            state_version=prior_map.state_version + 1,
            prior_map_head_digest=_digest(prior_map),
            entries=tuple(sorted(entries.items())),
            transition_fact_digest=reservation_digest,
        )
        installed_outer = replace(
            prior_outer,
            state_version=prior_outer.state_version + 1,
            prior_outer_head_digest=_digest(prior_outer),
            grant_map_head_digest=_digest(installed_map),
            transition_fact_digest=reservation_digest,
        )
        self._install(
            transition_kind="CREATE_TRUSTED_DELIVERY_RELEASE_RESERVATION",
            operation_id=operation_id,
            prior_outer=prior_outer,
            installed_outer=installed_outer,
            installed_map=installed_map,
            changed_entries=((prior_entry, installed_entry),),
            objects=(
                reservation,
                read_scope,
                boundary_membership,
                read_authorization_decision,
                release_recipient_context,
                qualified_deadline_mapping,
                grant_currentness_evidence,
                expected_grant_currentness_state_cut,
                release_cas,
                validated_release_cas_receipt,
                retained_authorization_cut,
                *intents,
                activation.activation_receipt,
            ),
            specialized_builder=(lambda _context, _generic, _map, _selector: ()),
            commit_time=commit_time,
            deadline_intents=intents,
        )
        return reservation

    def _release_lineage_receipts(
        self,
        *,
        current_entry: TrustedDeliveryBoundaryGrantStateHead,
        pending_reservation: TrustedDeliveryReleaseReservation,
    ) -> tuple[
        TrustedDeliveryBoundaryGrantEnforcementReceipt,
        TrustedDeliveryBoundaryGrantActivationReceipt,
    ]:
        objects = _tuple_map(self.store.snapshot.objects)
        activation_receipt = objects.get(pending_reservation.activation_receipt_digest)
        activation_fact = objects.get(
            activation_receipt.activation_fact_digest
            if isinstance(
                activation_receipt,
                TrustedDeliveryBoundaryGrantActivationReceipt,
            )
            else ""
        )
        enforcement_receipts = tuple(
            value
            for value in objects.values()
            if isinstance(
                value,
                TrustedDeliveryBoundaryGrantEnforcementReceipt,
            )
            and isinstance(
                activation_receipt,
                TrustedDeliveryBoundaryGrantActivationReceipt,
            )
            and value.installed_entry_head_digest
            == activation_receipt.prior_entry_head_digest
            and value.preparation_fact_digest == current_entry.preparation_fact_digest
        )
        _require(
            isinstance(
                activation_receipt,
                TrustedDeliveryBoundaryGrantActivationReceipt,
            )
            and isinstance(
                activation_fact,
                TrustedDeliveryBoundaryGrantActivationFact,
            )
            and len(enforcement_receipts) == 1
            and current_entry.activation_fact_digest == _digest(activation_fact)
            and activation_receipt.activation_fact_digest
            == current_entry.activation_fact_digest
            and activation_fact.full_boundary_key == current_entry.full_boundary_key
            and activation_fact.prior_entry_head_digest
            == activation_receipt.prior_entry_head_digest
            == enforcement_receipts[0].installed_entry_head_digest
            and enforcement_receipts[0].preparation_fact_digest
            == current_entry.preparation_fact_digest,
            "release lineage does not select one exact preparation and "
            "activation receipt",
        )
        return enforcement_receipts[0], activation_receipt

    def release_to_outbox(
        self,
        *,
        reservation: TrustedDeliveryReleaseReservation,
        preparation: BoundaryPreparationResult,
        activation: BoundaryActivationResult,
        payload: bytes,
        commit_time: int,
    ) -> BoundaryReleaseResult:
        _require(
            type(payload) is bytes and 0 < len(payload) <= MAX_CANONICAL_STRING_CHARS,
            "release payload is empty, subclassed, or above the bounded result size",
        )
        pending_reservation = reservation
        prior_entry = self.entry(reservation.full_boundary_key)
        pending_reservation_digest = _digest(pending_reservation)
        _require(
            prior_entry is not None,
            "release lineage entry is absent",
        )
        (
            lineage_enforcement_receipt,
            lineage_activation_receipt,
        ) = self._release_lineage_receipts(
            current_entry=prior_entry,
            pending_reservation=pending_reservation,
        )
        _require(
            preparation.enforcement_receipt == lineage_enforcement_receipt
            and _digest(preparation.fact)
            == lineage_enforcement_receipt.preparation_fact_digest
            and _digest(preparation.installed_entry)
            == lineage_enforcement_receipt.installed_entry_head_digest
            and activation.activation_receipt == lineage_activation_receipt
            and _digest(activation.fact)
            == lineage_activation_receipt.activation_fact_digest
            and _digest(activation.installed_entry)
            == lineage_activation_receipt.installed_entry_head_digest,
            "caller-supplied preparation or activation result is not the "
            "installed release lineage",
        )
        if (
            prior_entry is not None
            and pending_reservation_digest
            not in prior_entry.pending_reservation_digests
        ):
            stored_objects = _tuple_map(self.store.snapshot.objects)
            matching_commitments = tuple(
                value
                for value in stored_objects.values()
                if isinstance(
                    value,
                    TrustedDeliveryReleaseOutboxCommitment,
                )
                and value.reservation_digest == pending_reservation_digest
            )
            if len(matching_commitments) == 1:
                existing_commitment = matching_commitments[0]
                existing_reservation = stored_objects.get(
                    existing_commitment.validated_release_reservation_digest
                )
                matching_outboxes = tuple(
                    value
                    for value in stored_objects.values()
                    if isinstance(value, TrustedDeliveryReleaseOutbox)
                    and value.outbox_commitment_digest == _digest(existing_commitment)
                )
                existing_outbox = (
                    matching_outboxes[0] if len(matching_outboxes) == 1 else None
                )
                existing_receipt = (
                    stored_objects.get(existing_outbox.release_receipt_digest)
                    if isinstance(existing_outbox, TrustedDeliveryReleaseOutbox)
                    else None
                )
                _require(
                    isinstance(
                        existing_reservation,
                        TrustedDeliveryReleaseReservation,
                    )
                    and isinstance(
                        existing_outbox,
                        TrustedDeliveryReleaseOutbox,
                    )
                    and isinstance(
                        existing_receipt,
                        TrustedDeliveryReleaseReceipt,
                    )
                    and existing_outbox.complete_payload == payload
                    and existing_outbox.payload_digest
                    == pending_reservation.payload_digest
                    and existing_outbox.payload_length
                    == pending_reservation.payload_length
                    and existing_receipt.enforcement_receipt_digest
                    == _digest(lineage_enforcement_receipt)
                    and existing_receipt.activation_receipt_digest
                    == _digest(lineage_activation_receipt),
                    "outbox retry differs from the atomically committed request",
                )
                return BoundaryReleaseResult(
                    pending_reservation=pending_reservation,
                    reservation=existing_reservation,
                    commitment=existing_commitment,
                    release_receipt=existing_receipt,
                    outbox_item=existing_outbox,
                )
        _require(
            prior_entry is not None and prior_entry.phase == "LIVE_BOUNDARY_GRANT",
            "only a current LIVE entry can release to outbox",
        )
        _require(
            pending_reservation_digest in prior_entry.pending_reservation_digests,
            "release reservation is not current",
        )
        _require(
            reservation.payload_digest == hashlib.sha256(payload).hexdigest()
            and reservation.payload_length == len(payload),
            "release payload differs from its reservation",
        )
        prior_outer = self.head
        prior_map = self.grant_map()
        decision_artifact_digest = reservation.read_authorization_decision_digest
        _require(
            decision_artifact_digest not in prior_outer.consumed_read_decision_digests,
            "release decision was consumed before atomic outbox commit",
        )
        prior_release_count = prior_outer.consumed_read_decision_digests.count(
            decision_artifact_digest
        )
        read_authorization_decision = self.store.object(
            decision_artifact_digest,
            SealedObserverReadAuthorizationDecision,
        )
        preparation_fact = self.store.object(
            prior_entry.preparation_fact_digest,
            TrustedDeliveryBoundaryGrantPreparationFact,
        )
        plan = self.store.object(
            preparation_fact.boundary_installation_plan_digest,
            ObserverGrantBoundaryInstallationPlan,
        )
        _require(
            prior_release_count < read_authorization_decision.maximum_release_count,
            "release quota changed after reservation",
        )
        actual_release_sequence = prior_outer.next_release_sequence
        actual_output_slot = prior_outer.next_output_slot
        release_identity = _uuid_for(
            (
                "release",
                self.member.identity,
                reservation.release_cas.release_idempotency_key,
                actual_release_sequence,
            )
        )
        _require(
            release_identity not in prior_outer.used_release_identities
            and actual_output_slot not in prior_outer.used_output_slots,
            "release identity or output slot was installed before outbox commit",
        )
        stable_item_id = _uuid_for(
            (
                "outbox-item",
                reservation.full_boundary_key,
                actual_release_sequence,
            )
        )
        _require(
            stable_item_id not in _tuple_map(prior_outer.outbox_items),
            "outbox item identity reused",
        )
        operation_id = _uuid_for(
            (
                "release-outbox",
                _digest(reservation),
                stable_item_id,
            )
        )
        grant_currentness_evidence = seal_grant_currentness_evidence(
            replace(
                reservation.grant_currentness_evidence,
                boundary_state_head_digest=_digest(prior_outer),
                grant_entry_head_digest=_digest(prior_entry),
                release_counter_state_digest="",
                state_version=prior_outer.state_version,
                prior_release_count=prior_release_count,
                verified_at=commit_time,
                local_grant_exclusive_not_after=(
                    prior_entry.deadline.boundary_release_not_after
                ),
                exclusive_not_after=(prior_entry.deadline.boundary_release_not_after),
                semantic_evidence_digest="",
                fixture_authentication_tag="",
            ),
            fixture_key=_READ_DECISION_SEAL_KEY,
        )
        expected_grant_currentness_state_cut = ExpectedGrantCurrentnessStateCut(
            boundary_state_head_digest=_digest(prior_outer),
            grant_entry_head_digest=_digest(prior_entry),
            state_version=prior_outer.state_version,
            prior_release_count=prior_release_count,
            grant_currentness_receipt_digest=reservation.activation_receipt_digest,
            local_grant_exclusive_not_after=(
                prior_entry.deadline.boundary_release_not_after
            ),
            evidence_artifact_digest=grant_currentness_artifact_digest(
                grant_currentness_evidence
            ),
        )
        release_ordinal = prior_release_count + 1
        release_cas = seal_release_cas(
            replace(
                reservation.release_cas,
                grant_currentness_evidence_artifact_digest=(
                    grant_currentness_artifact_digest(grant_currentness_evidence)
                ),
                prior_release_count=prior_release_count,
                release_ordinal=release_ordinal,
                prior_release_counter_state_digest=(
                    grant_currentness_evidence.release_counter_state_digest
                ),
                next_release_counter_state_digest=(
                    next_grant_release_counter_state_digest(
                        evidence=grant_currentness_evidence,
                        release_idempotency_key=(
                            reservation.release_cas.release_idempotency_key
                        ),
                        release_ordinal=release_ordinal,
                    )
                ),
                local_grant_not_after=(prior_entry.deadline.boundary_release_not_after),
                grant_currentness_not_after=(
                    grant_currentness_evidence.exclusive_not_after
                ),
                effective_release_not_after=min(
                    prior_entry.deadline.boundary_release_not_after,
                    grant_currentness_evidence.exclusive_not_after,
                    reservation.qualified_deadline_mapping.mapped_exclusive_not_after,
                    reservation.release_recipient_context.exclusive_not_after,
                ),
                cas_digest="",
            )
        )
        try:
            validated_release_cas_receipt = issue_validated_release_cas_receipt(
                release_cas,
                validation_event_id=_uuid_for(
                    ("atomic-release-cas-validation", operation_id)
                ),
                validator_identity=(
                    self.member.boundary_principal,
                    self.member.boundary_instance,
                ),
                scope=self.member.read_scope,
                membership=self.member.scope_membership,
                decision=read_authorization_decision,
                release_context=reservation.release_recipient_context,
                qualified_deadline_mapping=(reservation.qualified_deadline_mapping),
                grant_currentness_evidence=grant_currentness_evidence,
                expected_observer_identity=(
                    prior_entry.full_boundary_key.registry_key.requester_principal,
                    reservation.release_recipient_context.recipient_instance,
                ),
                expected_boundary_identity=(
                    self.member.boundary_principal,
                    self.member.boundary_instance,
                    self.member.deadline_policy_id,
                ),
                expected_authorization_audience=(
                    self.member.read_scope.authorization_audience
                ),
                expected_authorization_cut=(reservation.retained_authorization_cut),
                expected_issuer_identity=(
                    SERVER_PRINCIPAL,
                    SERVER_KEY_ID,
                    SERVER_STATE_INCARNATION,
                ),
                expected_release_recipient_identity=(
                    prior_entry.full_boundary_key.registry_key.requester_principal,
                    reservation.release_recipient_context.recipient_instance,
                ),
                expected_release_transport_context=(
                    reservation.expected_release_transport_context
                ),
                expected_local_security_state=(
                    self.member.security_state_digest,
                    plan.security_epoch,
                    plan.revocation_epoch,
                ),
                expected_release_context_artifact_digest=(
                    release_recipient_artifact_digest(
                        reservation.release_recipient_context
                    )
                ),
                expected_grant_currentness_state_cut=(
                    expected_grant_currentness_state_cut
                ),
                expected_deadline_mapping_state_cut=(
                    reservation.expected_deadline_mapping_state_cut
                ),
                release_idempotency_key=(
                    reservation.release_cas.release_idempotency_key
                ),
                expected_boundary_clock_incarnation=(
                    self.member.clock_mapping.boundary_clock_incarnation
                ),
                expected_mapping_policy_artifact_digest=_digest(
                    self.member.clock_mapping
                ),
                checked_at=commit_time,
                fixture_key=_READ_DECISION_SEAL_KEY,
            )
        except BridgeValidationError as exc:
            raise ProbeError(
                "atomic outbox commit could not refresh release authority"
            ) from exc
        intents = (
            self._deadline_intent(
                purpose=AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE,
                kind="BOUNDARY_GRANT_RELEASE_NOT_AFTER",
                deadline=release_cas.effective_release_not_after,
                transition_kind="COMMIT_TRUSTED_DELIVERY_RELEASE_OUTBOX",
                operation_id=operation_id,
            ),
        )
        reservation = replace(
            pending_reservation,
            release_sequence=actual_release_sequence,
            output_slot=actual_output_slot,
            release_authority_recheck_digest=_semantic_digest(
                "ncp.b01.TrustedDeliveryReleaseAuthorityRecheck@1",
                (
                    _digest(read_authorization_decision),
                    self.member.read_scope.scope_digest,
                    self.member.scope_membership.membership_digest,
                    _digest(prior_outer),
                    _digest(prior_entry),
                    commit_time,
                    operation_id,
                ),
            ),
            grant_currentness_evidence=grant_currentness_evidence,
            expected_grant_currentness_state_cut=(expected_grant_currentness_state_cut),
            release_cas=release_cas,
            validated_release_cas_receipt=validated_release_cas_receipt,
            deadline_intent_set_digest=_intent_set_digest(intents),
        )
        commitment = TrustedDeliveryReleaseOutboxCommitment(
            operation_id=operation_id,
            reservation_digest=_digest(pending_reservation),
            validated_release_reservation_digest=_digest(reservation),
            full_boundary_key=reservation.full_boundary_key,
            stable_item_id=stable_item_id,
            idempotency_key=_uuid_for(("transport-idempotency", stable_item_id)),
            attempt_namespace=_uuid_for(("attempt-namespace", stable_item_id)),
            payload_digest=reservation.payload_digest,
            payload_length=reservation.payload_length,
            output_slot=reservation.output_slot,
            canonical_scope_digest=reservation.canonical_scope_digest,
            boundary_scope_membership_digest=(
                reservation.boundary_scope_membership_digest
            ),
            read_authorization_decision_digest=(
                reservation.read_authorization_decision_digest
            ),
            release_authority_recheck_digest=(
                reservation.release_authority_recheck_digest
            ),
            deadline_intent_set_digest=_intent_set_digest(intents),
        )
        commitment_digest = _digest(commitment)
        installed_entry = replace(
            prior_entry,
            state_version=prior_entry.state_version + 1,
            prior_entry_head_digest=_digest(prior_entry),
            pending_reservation_digests=tuple(
                item
                for item in prior_entry.pending_reservation_digests
                if item != _digest(pending_reservation)
            ),
            installed_release_counter_state_digest=(
                reservation.release_cas.next_release_counter_state_digest
            ),
            released_outbox_commitment_digests=tuple(
                sorted(
                    (
                        *prior_entry.released_outbox_commitment_digests,
                        commitment_digest,
                    )
                )
            ),
            deadline_intent_set_digest=_intent_set_digest(intents),
        )
        entries = _tuple_map(prior_map.entries)
        entries[_digest(prior_entry.full_boundary_key)] = _digest(installed_entry)
        installed_map = replace(
            prior_map,
            state_version=prior_map.state_version + 1,
            prior_map_head_digest=_digest(prior_map),
            entries=tuple(sorted(entries.items())),
            transition_fact_digest=commitment_digest,
        )
        outbox_items = _tuple_map(prior_outer.outbox_items)
        outbox_items[stable_item_id] = commitment_digest
        _require(len(outbox_items) <= MAX_ITEMS, "outbox capacity exhausted")
        installed_release_counter_states = _tuple_map(
            prior_outer.installed_release_counter_state_digests
        )
        _require(
            decision_artifact_digest not in installed_release_counter_states,
            "release counter successor was already installed",
        )
        installed_release_counter_states[decision_artifact_digest] = (
            reservation.release_cas.next_release_counter_state_digest
        )
        installed_outer = replace(
            prior_outer,
            state_version=prior_outer.state_version + 1,
            prior_outer_head_digest=_digest(prior_outer),
            grant_map_head_digest=_digest(installed_map),
            next_release_sequence=_checked_add(
                prior_outer.next_release_sequence,
                1,
            ),
            next_output_slot=_checked_add(prior_outer.next_output_slot, 1),
            outbox_items=tuple(sorted(outbox_items.items())),
            used_release_identities=(
                *prior_outer.used_release_identities,
                release_identity,
            ),
            consumed_read_decision_digests=tuple(
                sorted(
                    (
                        *prior_outer.consumed_read_decision_digests,
                        decision_artifact_digest,
                    )
                )
            ),
            installed_release_counter_state_digests=tuple(
                sorted(installed_release_counter_states.items())
            ),
            used_output_slots=(
                *prior_outer.used_output_slots,
                reservation.output_slot,
            ),
            transition_fact_digest=commitment_digest,
        )
        built: dict[str, Any] = {}

        def specialized_builder(
            context: AtomicReceiptContext,
            generic: TrustedDeliveryReleaseStateCommitReceipt,
            map_receipt: TrustedDeliveryBoundaryGrantMapCommitReceipt,
            selector: InstalledTrustedDeliveryReleaseSelector,
        ) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
            committed_bridge_outbox_artifact = seal_committed_outbox_artifact(
                SyntheticCommittedObserverReadOutboxArtifact(
                    provenance_kind=(
                        "SYNTHETIC_ATOMICALLY_COMMITTED_OBSERVER_READ_OUTBOX"
                    ),
                    stable_outbox_item_id=stable_item_id,
                    exact_payload=payload,
                    stable_payload_digest=reservation.payload_digest,
                    payload_octet_length=reservation.payload_length,
                    release_cas_artifact_digest=(reservation.release_cas.cas_digest),
                    release_recipient_context_artifact_digest=(
                        release_recipient_artifact_digest(
                            reservation.release_recipient_context
                        )
                    ),
                    boundary_principal=self.member.boundary_principal,
                    boundary_instance=self.member.boundary_instance,
                    recipient_principal=reservation.requester_principal,
                    recipient_instance=(
                        reservation.release_recipient_context.recipient_instance
                    ),
                    canonical_scope_digest=reservation.canonical_scope_digest,
                    boundary_scope_membership_digest=(
                        reservation.boundary_scope_membership_digest
                    ),
                    release_idempotency_key=(
                        reservation.release_cas.release_idempotency_key
                    ),
                    transport_idempotency_key=commitment.idempotency_key,
                    release_ordinal=reservation.release_cas.release_ordinal,
                    installed_release_counter_state_digest=(
                        reservation.release_cas.next_release_counter_state_digest
                    ),
                    boundary_clock_incarnation=(
                        reservation.release_cas.boundary_clock_incarnation
                    ),
                    committed_at=context.exact_commit_time,
                    effective_release_not_after=(
                        reservation.release_cas.effective_release_not_after
                    ),
                    outbox_identity_digest="",
                    semantic_artifact_digest="",
                    fixture_authentication_tag="",
                ),
                fixture_key=_READ_DECISION_SEAL_KEY,
            )
            bridge_commit_receipt = seal_outbox_commit_receipt(
                SyntheticObserverReadOutboxCommitReceipt(
                    provenance_kind=("SYNTHETIC_ATOMIC_OBSERVER_READ_OUTBOX_COMMIT"),
                    transaction_id=operation_id,
                    boundary_principal=self.member.boundary_principal,
                    boundary_instance=self.member.boundary_instance,
                    boundary_clock_incarnation=(
                        reservation.release_cas.boundary_clock_incarnation
                    ),
                    prior_storage_state_head_digest=_digest(prior_outer),
                    installed_storage_state_head_digest="",
                    validated_release_cas_receipt_artifact_digest=(
                        validated_release_cas_receipt_artifact_digest(
                            reservation.validated_release_cas_receipt
                        )
                    ),
                    release_cas_artifact_digest=(reservation.release_cas.cas_digest),
                    committed_outbox_artifact_digest=(
                        committed_outbox_artifact_digest(
                            committed_bridge_outbox_artifact
                        )
                    ),
                    stable_outbox_item_id=stable_item_id,
                    outbox_identity_digest=(
                        committed_bridge_outbox_artifact.outbox_identity_digest
                    ),
                    installed_release_counter_state_digest=(
                        reservation.release_cas.next_release_counter_state_digest
                    ),
                    release_ordinal=reservation.release_cas.release_ordinal,
                    committed_at=context.exact_commit_time,
                    semantic_receipt_digest="",
                    fixture_authentication_tag="",
                ),
                fixture_key=_READ_DECISION_SEAL_KEY,
            )
            expected_bridge_commit_state_cut = (
                ExpectedCommittedObserverReadOutboxStateCut(
                    transaction_id=operation_id,
                    prior_storage_state_head_digest=_digest(prior_outer),
                    installed_storage_state_head_digest=(
                        bridge_commit_receipt.installed_storage_state_head_digest
                    ),
                    validated_release_cas_receipt_artifact_digest=(
                        validated_release_cas_receipt_artifact_digest(
                            reservation.validated_release_cas_receipt
                        )
                    ),
                    committed_outbox_artifact_digest=(
                        committed_outbox_artifact_digest(
                            committed_bridge_outbox_artifact
                        )
                    ),
                    commit_receipt_artifact_digest=(
                        outbox_commit_receipt_artifact_digest(bridge_commit_receipt)
                    ),
                )
            )
            release_receipt = TrustedDeliveryReleaseReceipt(
                outbox_commitment_digest=commitment_digest,
                prior_outer_head_digest=_digest(prior_outer),
                installed_outer_head_digest=_digest(installed_outer),
                prior_map_head_digest=_digest(prior_map),
                installed_map_head_digest=_digest(installed_map),
                prior_entry_head_digest=_digest(prior_entry),
                installed_entry_head_digest=_digest(installed_entry),
                installed_selector_version=context.selector_version,
                installed_selector_digest=_digest(selector),
                outer_commit_receipt_digest=_digest(generic),
                map_commit_receipt_digest=_digest(map_receipt),
                output_slot=reservation.output_slot,
                canonical_scope_digest=reservation.canonical_scope_digest,
                boundary_scope_membership_digest=(
                    reservation.boundary_scope_membership_digest
                ),
                read_authorization_decision_digest=(
                    reservation.read_authorization_decision_digest
                ),
                release_authority_recheck_digest=(
                    reservation.release_authority_recheck_digest
                ),
                enforcement_receipt_digest=_digest(lineage_enforcement_receipt),
                activation_receipt_digest=_digest(lineage_activation_receipt),
                deadline_intent_set_digest=_intent_set_digest(context.deadline_intents),
                deadline_conditions=context.deadline_conditions,
                bridge_validated_release_cas_receipt_artifact_digest=(
                    expected_bridge_commit_state_cut.validated_release_cas_receipt_artifact_digest
                ),
                bridge_commit_receipt_artifact_digest=(
                    expected_bridge_commit_state_cut.commit_receipt_artifact_digest
                ),
                bridge_prior_storage_state_head_digest=(
                    expected_bridge_commit_state_cut.prior_storage_state_head_digest
                ),
                bridge_installed_storage_state_head_digest=(
                    expected_bridge_commit_state_cut.installed_storage_state_head_digest
                ),
            )
            outbox = TrustedDeliveryReleaseOutbox(
                stable_item_id=stable_item_id,
                full_boundary_key=reservation.full_boundary_key,
                outbox_commitment_digest=commitment_digest,
                release_receipt_digest=_digest(release_receipt),
                idempotency_key=commitment.idempotency_key,
                attempt_namespace=commitment.attempt_namespace,
                payload_digest=reservation.payload_digest,
                payload_length=reservation.payload_length,
                complete_payload=payload,
                output_slot=reservation.output_slot,
                canonical_scope_digest=reservation.canonical_scope_digest,
                boundary_scope_membership_digest=(
                    reservation.boundary_scope_membership_digest
                ),
                read_authorization_decision_digest=(
                    reservation.read_authorization_decision_digest
                ),
                release_authority_recheck_digest=(
                    reservation.release_authority_recheck_digest
                ),
                committed_bridge_outbox_artifact=(committed_bridge_outbox_artifact),
                bridge_commit_receipt=bridge_commit_receipt,
                expected_bridge_commit_state_cut=(expected_bridge_commit_state_cut),
            )
            built.update({"receipt": release_receipt, "outbox": outbox})
            return (release_receipt,), (outbox,)

        self._install(
            transition_kind="COMMIT_TRUSTED_DELIVERY_RELEASE_OUTBOX",
            operation_id=operation_id,
            prior_outer=prior_outer,
            installed_outer=installed_outer,
            installed_map=installed_map,
            changed_entries=((prior_entry, installed_entry),),
            objects=(
                pending_reservation,
                reservation,
                commitment,
                lineage_enforcement_receipt,
                lineage_activation_receipt,
                *intents,
            ),
            specialized_builder=specialized_builder,
            commit_time=commit_time,
            deadline_intents=intents,
        )
        release_receipt = built["receipt"]
        outbox = built["outbox"]
        _require(
            isinstance(release_receipt, TrustedDeliveryReleaseReceipt)
            and isinstance(outbox, TrustedDeliveryReleaseOutbox),
            "release receipt/outbox factory did not run",
        )
        return BoundaryReleaseResult(
            pending_reservation=pending_reservation,
            reservation=reservation,
            commitment=commitment,
            release_receipt=release_receipt,
            outbox_item=outbox,
        )

    def start_external_drain(
        self,
        *,
        release: BoundaryReleaseResult,
        actual_dispatch_payload: bytes,
        dispatch_context: SyntheticAuthenticatedDispatchContext,
        expected_dispatch_destination_cut: ExpectedDispatchDestinationCut,
        expected_dispatch_context_artifact_digest: str,
        receiver_dedup_retry_proof: (SyntheticReceiverDeduplicationRetryProof | None),
        commit_time: int,
    ) -> TrustedDeliveryExternalTransportDrainFact:
        _require(
            type(actual_dispatch_payload) is bytes
            and len(actual_dispatch_payload) <= MAX_AUTHORITY_CONTENT_BYTES,
            "dispatch payload type or size is outside the exact bound",
        )
        key = release.outbox_item.full_boundary_key
        _require(
            self.store.object(
                _digest(release.outbox_item),
                TrustedDeliveryReleaseOutbox,
            )
            == release.outbox_item
            and self.store.object(
                _digest(release.release_receipt),
                TrustedDeliveryReleaseReceipt,
            )
            == release.release_receipt
            and self.store.object(
                _digest(release.commitment),
                TrustedDeliveryReleaseOutboxCommitment,
            )
            == release.commitment,
            "drain input is not the exact durably committed release bundle",
        )
        release_transitions = tuple(
            transition
            for transition in self.store.snapshot.transitions
            if transition.transition_kind == "COMMIT_TRUSTED_DELIVERY_RELEASE_OUTBOX"
            and _digest(release.outbox_item) in transition.co_committed_object_digests
        )
        _require(
            len(release_transitions) == 1
            and _digest(release.release_receipt)
            in release_transitions[0].specialized_receipt_digests,
            "outbox item and release receipt are not one winning atomic bundle",
        )
        _require(
            release.outbox_item.release_receipt_digest
            == _digest(release.release_receipt)
            and release.outbox_item.outbox_commitment_digest
            == _digest(release.commitment)
            and release.release_receipt.outbox_commitment_digest
            == _digest(release.commitment)
            and release.outbox_item.payload_digest
            == hashlib.sha256(release.outbox_item.complete_payload).hexdigest()
            and release.outbox_item.payload_length
            == len(release.outbox_item.complete_payload),
            "committed outbox item has a broken receipt/commitment/payload DAG",
        )
        retained_read_chain = (
            release.commitment.canonical_scope_digest,
            release.commitment.boundary_scope_membership_digest,
            release.commitment.read_authorization_decision_digest,
            release.commitment.release_authority_recheck_digest,
        )
        _require(
            retained_read_chain
            == (
                release.release_receipt.canonical_scope_digest,
                release.release_receipt.boundary_scope_membership_digest,
                release.release_receipt.read_authorization_decision_digest,
                release.release_receipt.release_authority_recheck_digest,
            )
            == (
                release.outbox_item.canonical_scope_digest,
                release.outbox_item.boundary_scope_membership_digest,
                release.outbox_item.read_authorization_decision_digest,
                release.outbox_item.release_authority_recheck_digest,
            ),
            "committed release bundle substituted its read-decision chain",
        )
        prior_entry = self.entry(key)
        _require(
            prior_entry is not None
            and prior_entry.phase in {"LIVE_BOUNDARY_GRANT", "TERMINAL_BOUNDARY_GRANT"},
            "drain start requires a retained LIVE or TERMINAL item",
        )
        if prior_entry.phase == "TERMINAL_BOUNDARY_GRANT":
            terminal_fact = self.store.object(
                prior_entry.terminal_fact_digest or "",
                TrustedDeliveryBoundaryTerminalTransitionFact,
            )
            terminal_transitions = tuple(
                transition
                for transition in self.store.snapshot.transitions
                if transition.transition_kind == "TERMINATE_BOUNDARY_GRANT"
                and transition.operation_id == terminal_fact.operation_id
            )
            _require(
                len(terminal_transitions) == 1
                and terminal_fact.full_boundary_key == key
                and terminal_fact.prior_entry_head_digest
                == prior_entry.prior_entry_head_digest
                and _digest(release.commitment)
                in terminal_fact.retained_outbox_item_digests,
                "terminal drain authority has a substituted fact or lineage",
            )
            _require(
                terminal_fact.cause in {"SERVER_TERMINAL", "SERVER_RENEWAL_FENCE"},
                "terminal retention is evidence only and does not authorize "
                "dispatch for this terminal cause",
            )
        _require(
            _digest(release.commitment)
            in prior_entry.released_outbox_commitment_digests,
            "drain item was not released under this grant",
        )
        prior_outer = self.head
        prior_map = self.grant_map()
        _require(
            _tuple_map(prior_outer.outbox_items).get(release.outbox_item.stable_item_id)
            == _digest(release.commitment),
            "outer state does not own this exact outbox item",
        )
        prior_dispositions = sorted(
            [
                self.store.object(
                    digest,
                    TrustedDeliveryExternalTransportDisposition,
                )
                for _identity, digest in prior_outer.drain_dispositions
                if self.store.object(
                    digest,
                    TrustedDeliveryExternalTransportDisposition,
                ).stable_item_id
                == release.outbox_item.stable_item_id
            ],
            key=lambda item: item.attempt_sequence,
        )
        if not prior_dispositions:
            _require(
                receiver_dedup_retry_proof is None,
                "first dispatch attempt carries an unsolicited retry proof",
            )
            attempt_sequence = 1
        else:
            prior_disposition = prior_dispositions[-1]
            prior_fact = self.store.object(
                prior_disposition.drain_fact_digest,
                TrustedDeliveryExternalTransportDrainFact,
            )
            _require(
                all(
                    disposition.outcome == "AMBIGUOUS_AFTER_EXTERNAL_TRANSPORT"
                    and not disposition.no_resend_right
                    for disposition in prior_dispositions
                )
                and receiver_dedup_retry_proof is not None,
                "definitive outcome or absent receiver deduplication proof "
                "forbids dispatch retry",
            )
            validate_receiver_deduplication_retry_proof(
                receiver_dedup_retry_proof,
                outbox=release.outbox_item,
                prior_fact=prior_fact,
                prior_disposition=prior_disposition,
                expected_destination_cut=expected_dispatch_destination_cut,
            )
            attempt_sequence = _checked_add(
                prior_disposition.attempt_sequence,
                1,
            )
        _require(
            prior_outer.next_attempt_sequence <= MAX_ATTEMPTS,
            "attempt allocator exhausted",
        )
        attempt_identity = _uuid_for(
            (
                release.outbox_item.attempt_namespace,
                attempt_sequence,
                prior_outer.next_attempt_sequence,
            )
        )
        _require(
            attempt_identity not in prior_outer.used_attempt_identities,
            "attempt identity reused",
        )
        operation_id = _uuid_for(
            (
                "start-drain",
                release.outbox_item.stable_item_id,
                attempt_identity,
            )
        )
        expected_boundary_identity = (
            self.member.boundary_principal,
            self.member.boundary_instance,
            self.member.deadline_policy_id,
        )
        _require(
            dispatch_context.verified_at
            >= release.outbox_item.committed_bridge_outbox_artifact.committed_at,
            "dispatch context predates the committed outbox",
        )
        try:
            validate_dispatch_context(
                dispatch_context,
                scope=self.member.read_scope,
                membership=self.member.scope_membership,
                release_context=release.reservation.release_recipient_context,
                release_cas=release.reservation.release_cas,
                validated_release_cas_receipt=(
                    release.reservation.validated_release_cas_receipt
                ),
                committed_outbox=(release.outbox_item.committed_bridge_outbox_artifact),
                commit_receipt=release.outbox_item.bridge_commit_receipt,
                expected_commit_state_cut=(
                    release.outbox_item.expected_bridge_commit_state_cut
                ),
                expected_boundary_identity=expected_boundary_identity,
                expected_recipient_identity=(
                    release.reservation.requester_principal,
                    release.reservation.release_recipient_context.recipient_instance,
                ),
                expected_release_transport_context=(
                    release.reservation.expected_release_transport_context
                ),
                expected_release_security_state=(
                    self.member.security_state_digest,
                    release.reservation.release_recipient_context.local_security_epoch,
                    release.reservation.release_recipient_context.local_revocation_epoch,
                ),
                expected_boundary_clock_incarnation=(
                    self.member.clock_mapping.boundary_clock_incarnation
                ),
                expected_release_context_artifact_digest=(
                    release_recipient_artifact_digest(
                        release.reservation.release_recipient_context
                    )
                ),
                release_context_checked_at=(
                    release.reservation.release_recipient_context.verified_at
                ),
                expected_stable_outbox_item_id=(release.outbox_item.stable_item_id),
                actual_dispatch_payload=actual_dispatch_payload,
                expected_committed_outbox_artifact_digest=(
                    committed_outbox_artifact_digest(
                        release.outbox_item.committed_bridge_outbox_artifact
                    )
                ),
                expected_dispatch_attempt_id=attempt_identity,
                expected_transport_idempotency_key=(
                    release.outbox_item.idempotency_key
                ),
                expected_local_security_state=(
                    self.member.security_state_digest,
                    release.reservation.release_recipient_context.local_security_epoch,
                    release.reservation.release_recipient_context.local_revocation_epoch,
                ),
                expected_destination_cut=expected_dispatch_destination_cut,
                expected_dispatch_context_artifact_digest=(
                    expected_dispatch_context_artifact_digest
                ),
                checked_at=commit_time,
                fixture_key=_READ_DECISION_SEAL_KEY,
            )
        except BridgeValidationError as exc:
            raise ProbeError("external drain dispatch context is invalid") from exc
        fact = TrustedDeliveryExternalTransportDrainFact(
            operation_id=operation_id,
            stable_item_id=release.outbox_item.stable_item_id,
            full_boundary_key=key,
            exact_outbox_item_digest=_digest(release.outbox_item),
            idempotency_key=release.outbox_item.idempotency_key,
            actual_dispatch_payload=actual_dispatch_payload,
            dispatch_context=dispatch_context,
            expected_dispatch_destination_cut=(expected_dispatch_destination_cut),
            dispatch_context_artifact_digest=dispatch_artifact_digest(dispatch_context),
            attempt_identity=attempt_identity,
            attempt_sequence=attempt_sequence,
            canonical_scope_digest=release.outbox_item.canonical_scope_digest,
            boundary_scope_membership_digest=(
                release.outbox_item.boundary_scope_membership_digest
            ),
            read_authorization_decision_digest=(
                release.outbox_item.read_authorization_decision_digest
            ),
            release_authority_recheck_digest=(
                release.outbox_item.release_authority_recheck_digest
            ),
            receiver_dedup_retry_proof_digest=(
                None
                if receiver_dedup_retry_proof is None
                else _digest(receiver_dedup_retry_proof)
            ),
        )
        fact_digest = _digest(fact)
        _require(
            not any(
                self.store.object(
                    digest,
                    TrustedDeliveryExternalTransportDrainFact,
                ).stable_item_id
                == fact.stable_item_id
                for _identity, digest in prior_outer.drain_facts
            ),
            "an external drain attempt is already active for this item",
        )
        installed_entry = replace(
            prior_entry,
            state_version=prior_entry.state_version + 1,
            prior_entry_head_digest=_digest(prior_entry),
            active_drain_fact_digests=tuple(
                sorted((*prior_entry.active_drain_fact_digests, fact_digest))
            ),
            deadline_intent_set_digest=None,
        )
        entries = _tuple_map(prior_map.entries)
        entries[_digest(key)] = _digest(installed_entry)
        installed_map = replace(
            prior_map,
            state_version=prior_map.state_version + 1,
            prior_map_head_digest=_digest(prior_map),
            entries=tuple(sorted(entries.items())),
            transition_fact_digest=fact_digest,
        )
        drain_facts = _tuple_map(prior_outer.drain_facts)
        drain_facts[attempt_identity] = fact_digest
        installed_outer = replace(
            prior_outer,
            state_version=prior_outer.state_version + 1,
            prior_outer_head_digest=_digest(prior_outer),
            grant_map_head_digest=_digest(installed_map),
            next_attempt_sequence=_checked_add(
                prior_outer.next_attempt_sequence,
                1,
            ),
            drain_facts=tuple(sorted(drain_facts.items())),
            used_attempt_identities=_append_unique_attempt_identity(
                prior_outer.used_attempt_identities,
                attempt_identity,
            ),
            transition_fact_digest=fact_digest,
        )
        self._install(
            transition_kind="START_EXTERNAL_TRANSPORT_DRAIN",
            operation_id=operation_id,
            prior_outer=prior_outer,
            installed_outer=installed_outer,
            installed_map=installed_map,
            changed_entries=((prior_entry, installed_entry),),
            objects=(
                fact,
                release.outbox_item,
                release.release_receipt,
                release.reservation,
                *(
                    ()
                    if receiver_dedup_retry_proof is None
                    else (receiver_dedup_retry_proof,)
                ),
            ),
            specialized_builder=(lambda _context, _generic, _map, _selector: ()),
            commit_time=commit_time,
        )
        return fact

    def enqueue_external_transport_for_test(
        self,
        *,
        fact: TrustedDeliveryExternalTransportDrainFact,
        exact_payload: bytes,
        enqueue_time: int,
    ) -> _SyntheticExternalTransportEnqueueRecord:
        """Execute the synthetic physical enqueue under the authority CAS lock."""

        return self.store.enqueue_external_transport_for_test(
            fact=fact,
            exact_payload=exact_payload,
            trusted_clock_sample=enqueue_time,
        )

    def resolve_external_drain(
        self,
        *,
        fact: TrustedDeliveryExternalTransportDrainFact,
        outcome: str,
        transport_evidence: (SyntheticAuthenticatedTransportDispositionEvidence | None),
        commit_time: int,
    ) -> TrustedDeliveryExternalTransportDisposition:
        self.store.require_external_transport_enqueue_for_test(fact)
        _require(
            outcome
            in {
                "DELIVERED",
                "REJECTED",
                "AMBIGUOUS_AFTER_EXTERNAL_TRANSPORT",
            },
            "unknown external transport disposition",
        )
        if outcome in {"DELIVERED", "REJECTED"}:
            validate_transport_disposition_evidence(
                transport_evidence,
                fact=fact,
                outcome=outcome,
                commit_time=commit_time,
                commit_clock_incarnation=self.store.snapshot.clock_incarnation,
            )
        else:
            _require(
                transport_evidence is None,
                "ambiguous transport result carries a definitive evidence claim",
            )
        prior_entry = self.entry(fact.full_boundary_key)
        _require(
            prior_entry is not None
            and _digest(fact) in prior_entry.active_drain_fact_digests,
            "drain resolution does not consume a current active attempt",
        )
        prior_outer = self.head
        prior_map = self.grant_map()
        _require(
            _tuple_map(prior_outer.drain_facts).get(fact.attempt_identity)
            == _digest(fact),
            "outer active-attempt root mismatch",
        )
        disposition = TrustedDeliveryExternalTransportDisposition(
            drain_fact_digest=_digest(fact),
            dispatch_context_artifact_digest=fact.dispatch_context_artifact_digest,
            stable_item_id=fact.stable_item_id,
            attempt_identity=fact.attempt_identity,
            attempt_sequence=fact.attempt_sequence,
            outcome=outcome,
            canonical_scope_digest=fact.canonical_scope_digest,
            boundary_scope_membership_digest=(fact.boundary_scope_membership_digest),
            read_authorization_decision_digest=(
                fact.read_authorization_decision_digest
            ),
            release_authority_recheck_digest=fact.release_authority_recheck_digest,
            authenticated_transport_evidence_digest=(
                None if transport_evidence is None else _digest(transport_evidence)
            ),
            no_resend_right=(
                outcome
                in {
                    "DELIVERED",
                    "REJECTED",
                }
            ),
        )
        disposition_digest = _digest(disposition)
        installed_entry = replace(
            prior_entry,
            state_version=prior_entry.state_version + 1,
            prior_entry_head_digest=_digest(prior_entry),
            active_drain_fact_digests=tuple(
                item
                for item in prior_entry.active_drain_fact_digests
                if item != _digest(fact)
            ),
            terminal_disposition_digests=tuple(
                sorted(
                    (
                        *prior_entry.terminal_disposition_digests,
                        disposition_digest,
                    )
                )
            ),
            deadline_intent_set_digest=None,
        )
        entries = _tuple_map(prior_map.entries)
        entries[_digest(fact.full_boundary_key)] = _digest(installed_entry)
        installed_map = replace(
            prior_map,
            state_version=prior_map.state_version + 1,
            prior_map_head_digest=_digest(prior_map),
            entries=tuple(sorted(entries.items())),
            transition_fact_digest=disposition_digest,
        )
        active = _tuple_map(prior_outer.drain_facts)
        active.pop(fact.attempt_identity)
        dispositions = _tuple_map(prior_outer.drain_dispositions)
        dispositions[fact.attempt_identity] = disposition_digest
        installed_outer = replace(
            prior_outer,
            state_version=prior_outer.state_version + 1,
            prior_outer_head_digest=_digest(prior_outer),
            grant_map_head_digest=_digest(installed_map),
            drain_facts=tuple(sorted(active.items())),
            drain_dispositions=tuple(sorted(dispositions.items())),
            transition_fact_digest=disposition_digest,
        )
        self._install(
            transition_kind="RESOLVE_EXTERNAL_TRANSPORT_DRAIN",
            operation_id=_uuid_for(("resolve-drain", fact.attempt_identity, outcome)),
            prior_outer=prior_outer,
            installed_outer=installed_outer,
            installed_map=installed_map,
            changed_entries=((prior_entry, installed_entry),),
            objects=(
                fact,
                disposition,
                *((transport_evidence,) if transport_evidence is not None else ()),
            ),
            specialized_builder=(lambda _context, _generic, _map, _selector: ()),
            commit_time=commit_time,
        )
        return disposition

    def terminalize(
        self,
        *,
        key: TrustedDeliveryBoundaryGrantKey,
        cause: str,
        server: ObserverAuthorizationServer | None,
        server_terminal: ServerTerminalResult | None,
        renewal_fence: ObserverGrantRenewalPredecessorFenceReceipt | None,
        commit_time: int,
    ) -> BoundaryTerminalResult:
        supported_causes = {
            "SERVER_TERMINAL",
            "SERVER_RENEWAL_FENCE",
            "LOCAL_FIXED_DEADLINE_EXPIRED",
        }
        _require(
            type(cause) is str and cause in supported_causes,
            "boundary terminal cause lacks closed typed authority evidence",
        )
        prior_entry = self.entry(key)
        _require(prior_entry is not None, "boundary terminal key is absent")
        _boundary_transition_guard(
            "TERMINATE_BOUNDARY_GRANT",
            prior_entry.phase,
            "TERMINAL_BOUNDARY_GRANT",
        )
        server_terminal_digest: str | None = None
        fence_digest: str | None = None
        selected_server_snapshot: ImmutableAuthoritySnapshot | None = None
        if cause == "SERVER_TERMINAL":
            _require(
                type(server) is ObserverAuthorizationServer
                and type(server_terminal) is ServerTerminalResult
                and renewal_fence is None,
                "server terminal cause lacks its unique authority anchor",
            )
            (
                selected_server_snapshot,
                server_terminal_digest,
            ) = _validate_server_terminal_anchor(
                server,
                server_terminal,
                expected_key=key,
            )
        elif cause == "SERVER_RENEWAL_FENCE":
            _require(
                type(server) is ObserverAuthorizationServer
                and type(renewal_fence) is ObserverGrantRenewalPredecessorFenceReceipt
                and server_terminal is None,
                "renewal fence cause lacks exact G0 authority",
            )
            (
                selected_server_snapshot,
                fence_digest,
            ) = _validate_server_renewal_fence_anchor(
                server,
                renewal_fence,
                expected_key=key,
            )
        else:
            _require(
                server is None and server_terminal is None and renewal_fence is None,
                "local expiry cause carries an irrelevant server authority anchor",
            )
        prior_outer = self.head
        prior_map = self.grant_map()
        operation_id = _uuid_for(
            (
                "boundary-terminal",
                _digest(prior_entry),
                cause,
                server_terminal_digest,
                fence_digest,
            )
        )
        intents: tuple[AuthorizationDeadlineConditionIntent, ...] = ()
        if cause == "LOCAL_FIXED_DEADLINE_EXPIRED":
            intents = (
                self._deadline_intent(
                    purpose=EXPIRY_AT_OR_AFTER_EXCLUSIVE_DEADLINE,
                    kind="BOUNDARY_GRANT_RELEASE_NOT_AFTER",
                    deadline=prior_entry.deadline.boundary_release_not_after,
                    transition_kind="TERMINATE_BOUNDARY_GRANT",
                    operation_id=operation_id,
                ),
            )
        fact = TrustedDeliveryBoundaryTerminalTransitionFact(
            operation_id=operation_id,
            full_boundary_key=key,
            cause=cause,
            server_terminal_receipt_digest=server_terminal_digest,
            renewal_fence_receipt_digest=fence_digest,
            prior_outer_head_digest=_digest(prior_outer),
            prior_map_head_digest=_digest(prior_map),
            prior_entry_head_digest=_digest(prior_entry),
            deadline=prior_entry.deadline,
            canceled_reservation_digests=(prior_entry.pending_reservation_digests),
            canceled_pre_release_commitment_digests=(
                prior_entry.pre_release_commitment_digests
            ),
            retained_outbox_item_digests=(
                prior_entry.released_outbox_commitment_digests
            ),
            retained_active_drain_fact_digests=(prior_entry.active_drain_fact_digests),
            deadline_intent_set_digest=(
                _intent_set_digest(intents) if intents else None
            ),
        )
        installed_entry = replace(
            prior_entry,
            state_version=prior_entry.state_version + 1,
            prior_entry_head_digest=_digest(prior_entry),
            phase="TERMINAL_BOUNDARY_GRANT",
            terminal_fact_digest=_digest(fact),
            pending_reservation_digests=(),
            pre_release_commitment_digests=(),
            canceled_reservation_tombstones=tuple(
                sorted(
                    (
                        *prior_entry.canceled_reservation_tombstones,
                        *prior_entry.pending_reservation_digests,
                        *prior_entry.pre_release_commitment_digests,
                    )
                )
            ),
            deadline_intent_set_digest=(
                _intent_set_digest(intents) if intents else None
            ),
        )
        entries = _tuple_map(prior_map.entries)
        entries[_digest(key)] = _digest(installed_entry)
        installed_map = replace(
            prior_map,
            state_version=prior_map.state_version + 1,
            prior_map_head_digest=_digest(prior_map),
            entries=tuple(sorted(entries.items())),
            transition_fact_digest=_digest(fact),
        )
        installed_outer = replace(
            prior_outer,
            state_version=prior_outer.state_version + 1,
            prior_outer_head_digest=_digest(prior_outer),
            grant_map_head_digest=_digest(installed_map),
            transition_fact_digest=_digest(fact),
        )
        built: dict[str, Any] = {}

        def specialized_builder(
            context: AtomicReceiptContext,
            generic: TrustedDeliveryReleaseStateCommitReceipt,
            map_receipt: TrustedDeliveryBoundaryGrantMapCommitReceipt,
            selector: InstalledTrustedDeliveryReleaseSelector,
        ) -> tuple[Any, ...]:
            receipt = TrustedDeliveryBoundaryTerminalInstallationReceipt(
                bulk_envelope_digest=None,
                terminal_fact_digest=_digest(fact),
                full_boundary_key=key,
                prior_outer_head_digest=_digest(prior_outer),
                installed_outer_head_digest=_digest(installed_outer),
                prior_map_head_digest=_digest(prior_map),
                installed_map_head_digest=_digest(installed_map),
                prior_entry_head_digest=_digest(prior_entry),
                installed_entry_head_digest=_digest(installed_entry),
                installed_selector_version=context.selector_version,
                installed_selector_digest=_digest(selector),
                outer_commit_receipt_digest=_digest(generic),
                map_commit_receipt_digest=_digest(map_receipt),
                canceled_reservation_digests=(fact.canceled_reservation_digests),
                retained_outbox_item_digests=(fact.retained_outbox_item_digests),
                retained_active_drain_fact_digests=(
                    fact.retained_active_drain_fact_digests
                ),
                deadline_conditions=context.deadline_conditions,
                signer_principal=context.authority_principal,
                signer_key_id=context.signing_key_id,
                signer_security_state_digest=context.security_state_digest,
            )
            built["receipt"] = receipt
            return (receipt,)

        self._install(
            transition_kind="TERMINATE_BOUNDARY_GRANT",
            operation_id=operation_id,
            prior_outer=prior_outer,
            installed_outer=installed_outer,
            installed_map=installed_map,
            changed_entries=((prior_entry, installed_entry),),
            objects=(
                fact,
                *intents,
                *(
                    (selected_server_snapshot,)
                    if selected_server_snapshot is not None
                    else ()
                ),
                *(
                    (
                        server_terminal.transition_fact,
                        server_terminal.terminal_receipt,
                        server_terminal.reattachment_policy_result,
                        server_terminal.installed_terminal_head,
                    )
                    if server_terminal is not None
                    else ()
                ),
                *((renewal_fence,) if renewal_fence is not None else ()),
            ),
            specialized_builder=specialized_builder,
            commit_time=commit_time,
            deadline_intents=intents,
        )
        receipt = built["receipt"]
        _require(
            isinstance(
                receipt,
                TrustedDeliveryBoundaryTerminalInstallationReceipt,
            ),
            "boundary terminal receipt factory did not run",
        )
        return BoundaryTerminalResult(
            fact=fact,
            receipt=receipt,
            installed_entry=installed_entry,
        )


def _validate_transition_semantics(
    *,
    prior_state: Any | None,
    installed_state: Any,
    staged_objects: Mapping[str, Any],
    context: AtomicReceiptContext,
    bundle: AtomicReceiptBundle,
) -> None:
    """Recompute type-specific currentness and transitive receipt links."""
    specialized = bundle.specialized_payloads
    if context.store_id == "observer-authorization-server":
        _require(
            isinstance(installed_state, ObserverAuthorizationStateHead),
            "server selector installed a non-server state",
        )
        _require(
            isinstance(
                bundle.generic_commit_payload,
                ObserverAuthorizationStateCommitReceipt,
            )
            and isinstance(
                bundle.selector,
                InstalledObserverAuthorizationStateSelector,
            ),
            "server generic/selector type mismatch",
        )
        _require(
            specialized
            and isinstance(specialized[0], ObserverGrantRegistryCommitReceipt),
            "server transaction lacks exact registry commit",
        )
        registry_receipt = specialized[0]
        installed_registry = staged_objects.get(
            installed_state.observer_grant_registry_head_digest
        )
        _require(
            isinstance(installed_registry, ObserverGrantRegistryHead),
            "installed server registry root is absent",
        )
        prior_registry: ObserverGrantRegistryHead | None = None
        if prior_state is not None:
            _require(
                isinstance(prior_state, ObserverAuthorizationStateHead),
                "server prior state has wrong type",
            )
            prior_registry_value = staged_objects.get(
                prior_state.observer_grant_registry_head_digest
            )
            _require(
                isinstance(prior_registry_value, ObserverGrantRegistryHead),
                "server prior registry root is absent",
            )
            prior_registry = prior_registry_value
        _require(
            registry_receipt.installed_registry_head_digest
            == _digest(installed_registry)
            and registry_receipt.prior_registry_head_digest
            == (None if prior_registry is None else _digest(prior_registry)),
            "server registry commit roots mismatch",
        )
        installed_entries = _tuple_map(installed_registry.entries)
        prior_entries = (
            {} if prior_registry is None else _tuple_map(prior_registry.entries)
        )
        _require(
            installed_state.prior_authorization_head_digest
            == (None if prior_state is None else _digest(prior_state))
            and installed_state.state_version
            == (1 if prior_state is None else prior_state.state_version + 1),
            "server outer state ancestry/version mismatch",
        )
        if prior_state is not None:
            _require(
                (
                    installed_state.server_principal,
                    installed_state.authority_realm_key,
                    installed_state.logical_session,
                    installed_state.session_generation,
                    installed_state.state_incarnation,
                    installed_state.descriptor_revision,
                    installed_state.descriptor_digest,
                    installed_state.privacy_policy_digest,
                    installed_state.security_state_digest,
                    installed_state.security_epoch,
                    installed_state.revocation_epoch,
                    installed_state.default_deny_manifest_digest,
                    installed_state.coordinator_clock_policy_id,
                    installed_state.coordinator_clock_incarnation,
                )
                == (
                    prior_state.server_principal,
                    prior_state.authority_realm_key,
                    prior_state.logical_session,
                    prior_state.session_generation,
                    prior_state.state_incarnation,
                    prior_state.descriptor_revision,
                    prior_state.descriptor_digest,
                    prior_state.privacy_policy_digest,
                    prior_state.security_state_digest,
                    prior_state.security_epoch,
                    prior_state.revocation_epoch,
                    prior_state.default_deny_manifest_digest,
                    prior_state.coordinator_clock_policy_id,
                    prior_state.coordinator_clock_incarnation,
                ),
                "server authority/realm/session/descriptor/manifest/security "
                "coordinates drifted outside a closed transition",
            )
        _require(
            installed_registry.prior_registry_head_digest
            == (None if prior_registry is None else _digest(prior_registry))
            and installed_registry.state_version
            == (1 if prior_registry is None else prior_registry.state_version + 1),
            "server registry ancestry/version mismatch",
        )
        _require(
            registry_receipt.transition_kind
            == (
                "GRANT_REGISTRY_GENESIS_FROM_UNINITIALIZED"
                if prior_registry is None
                else context.transition_kind
            ),
            "server registry commit transition mismatch",
        )
        installed_entry: ObserverGrantLedgerHead | None = None
        if registry_receipt.installed_entry_head_digest is not None:
            installed_entry = staged_objects.get(
                registry_receipt.installed_entry_head_digest
            )
            _require(
                isinstance(installed_entry, ObserverGrantLedgerHead),
                "server registry commit entry is absent",
            )
            stable_digest = _digest(installed_entry.registry_key)
            _require(
                installed_entries.get(stable_digest)
                == registry_receipt.installed_entry_head_digest,
                "server receipt entry is not in installed registry",
            )
            expected_prior = prior_entries.get(stable_digest)
            _require(
                registry_receipt.prior_entry_head_digest == expected_prior,
                "server receipt keyed predecessor mismatch",
            )
            for sibling, value in prior_entries.items():
                if sibling != stable_digest:
                    _require(
                        installed_entries.get(sibling) == value,
                        "server receipt failed sibling preservation",
                    )
            expected_entries = dict(prior_entries)
            expected_entries[stable_digest] = _digest(installed_entry)
            _require(
                installed_entries == expected_entries,
                "server registry mutation is not exactly one declared key",
            )
            _require(
                registry_receipt.sibling_preservation_digest
                == _digest(
                    tuple(
                        sorted(
                            (key, value)
                            for key, value in installed_entries.items()
                            if key != stable_digest
                        )
                    )
                ),
                "server sibling-preservation root mismatch",
            )
        else:
            _require(
                prior_registry is None
                and not installed_entries
                and registry_receipt.prior_entry_head_digest is None,
                "server no-entry transition is not the unique empty genesis",
            )
        kind = context.transition_kind
        if kind == "OBSERVER_AUTHORIZATION_STATE_GENESIS_FROM_SESSION_CREATION":
            _require(
                prior_state is None
                and len(specialized) == 1
                and installed_entry is None,
                "server genesis shape is not unique",
            )
            allocation = staged_objects.get(
                installed_state.transition_fact_digest or ""
            )
            descriptor = staged_objects.get(installed_state.descriptor_digest)
            manifest = staged_objects.get(installed_state.default_deny_manifest_digest)
            _require(
                isinstance(allocation, ParentSelectorAllocationReceipt)
                and type(descriptor) is ObserverDescriptor
                and type(manifest) is ObserverDefaultDenyManifest,
                "server genesis lacks its allocation, descriptor, or manifest",
            )
            _validate_default_deny_manifest(manifest)
            _require(
                descriptor.responder_principal == installed_state.server_principal
                and descriptor.authority_realm_key
                == installed_state.authority_realm_key
                and descriptor.logical_session == installed_state.logical_session
                and descriptor.session_generation == installed_state.session_generation
                and descriptor.descriptor_revision
                == installed_state.descriptor_revision
                and descriptor.privacy_policy_digest
                == installed_state.privacy_policy_digest
                and descriptor.security_state_digest
                == installed_state.security_state_digest
                and descriptor.security_epoch == installed_state.security_epoch
                and descriptor.revocation_epoch == installed_state.revocation_epoch
                and _digest(manifest) == installed_state.default_deny_manifest_digest
                and manifest.issuer_principal == installed_state.server_principal
                and manifest.issuer_key_id == context.signing_key_id,
                "server genesis descriptor mirror drift",
            )
        elif kind == "ATTACH_NEW_GRANT_LINEAGE":
            _require(
                len(specialized) == 2
                and isinstance(specialized[1], ObserverGrant)
                and installed_entry is not None,
                "attach lacks its exact grant and keyed successor",
            )
            grant = specialized[1]
            plan = staged_objects.get(installed_entry.boundary_installation_plan_digest)
            _require(
                isinstance(plan, ObserverGrantBoundaryInstallationPlan),
                "attach plan is absent",
            )
            _validate_plan_and_grant(plan, grant, installed_entry.full_boundary_key)
            _server_transition_guard(
                kind,
                "ABSENT",
                installed_entry.phase,
            )
            _require(
                registry_receipt.prior_entry_head_digest is None
                and installed_entry.prior_keyed_head_digest is None
                and installed_entry.state_version == 1
                and installed_entry.canonical_grant_digest == _digest(grant)
                and installed_entry.registry_key == plan.stable_registry_key
                and installed_state.transition_fact_digest == _digest(plan)
                and installed_entry.deadline_intent_set_digest is None,
                "attach keyed lineage is not a fresh exact plan/grant install",
            )
        elif kind == "ACTIVATE_PENDING_GRANT":
            set_receipt, proof, attached = specialized[1:]
            _require(
                isinstance(
                    set_receipt,
                    ObserverGrantBoundaryInstallationSetReceipt,
                )
                and isinstance(
                    proof,
                    ObserverGrantRegistryActivationEntryProof,
                )
                and isinstance(attached, ObserverAttached),
                "server activation specialized receipt types mismatch",
            )
            _require(
                proof.boundary_installation_set_receipt_digest == _digest(set_receipt)
                and attached.boundary_installation_set_receipt_digest
                == _digest(set_receipt)
                and proof.installed_keyed_head_digest
                == set_receipt.installed_keyed_head_digest,
                "server activation transitive receipt link mismatch",
            )
            installed_entry = staged_objects[set_receipt.installed_keyed_head_digest]
            _require(
                isinstance(installed_entry, ObserverGrantLedgerHead),
                "server activation installed entry is absent",
            )
            prior_entry = staged_objects.get(
                registry_receipt.prior_entry_head_digest or ""
            )
            _require(
                isinstance(prior_entry, ObserverGrantLedgerHead),
                "server activation prior entry is absent",
            )
            _server_transition_guard(
                kind,
                prior_entry.phase,
                installed_entry.phase,
            )
            commitment = staged_objects.get(
                installed_entry.activation_commitment_digest
            )
            _require(
                isinstance(
                    commitment,
                    ObserverGrantBoundaryInstallationCommitment,
                )
                and set_receipt.commitment_digest == _digest(commitment)
                and commitment.operation_id == context.operation_id
                and commitment.deadline_intent_set_digest
                == _intent_set_digest(context.deadline_intents),
                "server activation commitment DAG mismatch",
            )
            plan = staged_objects.get(installed_entry.boundary_installation_plan_digest)
            grant = staged_objects.get(installed_entry.canonical_grant_digest)
            capability_evidence_matches = tuple(
                item
                for item in staged_objects.values()
                if type(item) is ObserverReadCapabilityEvidence
                and _digest(item.capability) == attached.observer_read_capability_digest
            )
            capability_evidence = (
                capability_evidence_matches[0]
                if len(capability_evidence_matches) == 1
                else None
            )
            manifest = staged_objects.get(installed_state.default_deny_manifest_digest)
            _require(
                isinstance(plan, ObserverGrantBoundaryInstallationPlan)
                and isinstance(grant, ObserverGrant)
                and type(capability_evidence) is ObserverReadCapabilityEvidence
                and type(manifest) is ObserverDefaultDenyManifest,
                "server activation plan, grant, manifest, or unique capability "
                "evidence is absent",
            )
            read_capability = capability_evidence.capability
            manifest_entry = _validate_capability_evidence(
                capability_evidence,
                manifest=manifest,
                trusted_time=context.exact_commit_time,
            )
            _validate_plan_and_grant(plan, grant, installed_entry.full_boundary_key)
            _require(
                read_capability.observer_principal == grant.requester_principal
                and read_capability.manifest_session_scope
                == (grant.logical_session, grant.session_generation)
                and read_capability.authority_realm_key
                == installed_state.authority_realm_key
                and read_capability.default_deny_manifest_digest
                == installed_state.default_deny_manifest_digest
                and read_capability.operations == OBSERVER_READ_OPERATIONS
                and read_capability.exact_scope_digests == grant.exact_scope_digests
                and read_capability.exact_scope_digests
                == _manifest_scope_digests(manifest_entry)
                and read_capability.issued_at >= plan.server_request_time
                and read_capability.not_after
                <= installed_entry.effective_server_not_after
                and (
                    read_capability.security_state_digest,
                    read_capability.security_epoch,
                    read_capability.revocation_epoch,
                    read_capability.coordinator_clock_incarnation,
                )
                == (
                    installed_state.security_state_digest,
                    installed_state.security_epoch,
                    installed_state.revocation_epoch,
                    installed_state.coordinator_clock_incarnation,
                ),
                "recovered read capability is not the exact read-only grant",
            )
            _require(
                commitment.canonical_prepared_member_receipts
                == set_receipt.canonical_prepared_member_receipts
                and tuple(
                    item[0] for item in commitment.canonical_prepared_member_receipts
                )
                == tuple(member.identity for member in plan.boundary_members)
                and len(
                    {item[1] for item in commitment.canonical_prepared_member_receipts}
                )
                == len(plan.boundary_members),
                "recovered prepared receipt set is not an exact member bijection",
            )
            boundary_snapshots = tuple(
                item
                for item in staged_objects.values()
                if isinstance(item, ImmutableAuthoritySnapshot)
                and item.store_id.startswith("trusted-delivery-boundary:")
            )
            _require(
                len(boundary_snapshots) == len(plan.boundary_members),
                "server activation lacks one exact boundary snapshot per member",
            )
            for member, prepared_item in zip(
                plan.boundary_members,
                commitment.canonical_prepared_member_receipts,
                strict=True,
            ):
                identity, receipt_digest = prepared_item
                matches = tuple(
                    snapshot
                    for snapshot in boundary_snapshots
                    if snapshot.authority_principal == member.boundary_principal
                    and snapshot.store_id
                    == f"trusted-delivery-boundary:{member.boundary_instance}"
                )
                _require(
                    identity == member.identity and len(matches) == 1,
                    "prepared boundary snapshot identity mismatch",
                )
                boundary_snapshot = matches[0]
                _validate_atomic_snapshot(boundary_snapshot)
                boundary_objects = _tuple_map(boundary_snapshot.objects)
                enforcement = boundary_objects.get(receipt_digest)
                _require(
                    isinstance(
                        enforcement,
                        TrustedDeliveryBoundaryGrantEnforcementReceipt,
                    )
                    and enforcement.canonical_grant_digest == _digest(grant)
                    and enforcement.boundary_installation_plan_digest == _digest(plan),
                    "prepared boundary snapshot lacks its exact enforcement receipt",
                )
                _verify_signed_bytes(
                    enforcement,
                    _tuple_map(boundary_snapshot.signed_bytes)[receipt_digest],
                    expected_principal=member.boundary_principal,
                    expected_key_id=member.security_key_id,
                    expected_security_state=member.security_state_digest,
                )
                boundary_state = boundary_snapshot.state
                _require(
                    isinstance(boundary_state, TrustedDeliveryReleaseStateHead),
                    "prepared boundary snapshot has wrong selected state",
                )
                boundary_map = boundary_objects.get(
                    boundary_state.grant_map_head_digest
                )
                _require(
                    isinstance(
                        boundary_map,
                        TrustedDeliveryBoundaryGrantMapHead,
                    )
                    and _tuple_map(boundary_map.entries).get(
                        _digest(installed_entry.full_boundary_key)
                    )
                    == enforcement.installed_entry_head_digest,
                    "prepared enforcement receipt is not the boundary's current entry",
                )
        elif kind == "BEGIN_GRANT_RENEWAL":
            grant, fence = specialized[1:]
            _require(
                isinstance(grant, ObserverGrant)
                and isinstance(
                    fence,
                    ObserverGrantRenewalPredecessorFenceReceipt,
                ),
                "renewal artifact types mismatch",
            )
            _require(
                fence.registry_commit_receipt_digest == _digest(registry_receipt)
                and fence.deadline_intent_digest == _digest(context.deadline_intents[0])
                and fence.deadline_condition == context.deadline_conditions[0],
                "renewal fence transitive link mismatch",
            )
            installed_entry = staged_objects[
                fence.installed_g1_pending_keyed_head_digest
            ]
            _require(
                isinstance(installed_entry, ObserverGrantLedgerHead),
                "renewal installed entry is absent",
            )
            prior_entry = staged_objects.get(fence.consumed_g0_keyed_head_digest)
            plan = staged_objects.get(installed_entry.boundary_installation_plan_digest)
            renewal_fact = staged_objects.get(
                installed_entry.renewal_transition_fact_digest
            )
            _require(
                isinstance(prior_entry, ObserverGrantLedgerHead)
                and isinstance(plan, ObserverGrantBoundaryInstallationPlan)
                and isinstance(renewal_fact, ObserverGrantRenewalTransitionFact)
                and renewal_fact.operation_id == context.operation_id
                and renewal_fact.deadline_intent_set_digest
                == _intent_set_digest(context.deadline_intents),
                "renewal fact/candidate intent root mismatch",
            )
            _validate_plan_and_grant(plan, grant, installed_entry.full_boundary_key)
            _server_transition_guard(
                kind,
                prior_entry.phase,
                installed_entry.phase,
            )
            _require(
                renewal_fact.prior_g0_keyed_head_digest == _digest(prior_entry)
                and renewal_fact.candidate_plan_digest == _digest(plan)
                and renewal_fact.candidate_grant_digest == _digest(grant)
                and renewal_fact.expected_prior_selector_version
                == context.selector_version - 1
                and installed_state.transition_fact_digest == _digest(renewal_fact),
                "renewal predecessor/plan/grant/selector links mismatch",
            )
        elif kind == "TERMINATE_GRANT":
            receipt, policy = specialized[1:]
            _require(
                isinstance(receipt, ObserverGrantTerminalTransitionReceipt)
                and isinstance(policy, ObserverGrantReattachmentPolicyResult),
                "terminal specialized receipt types mismatch",
            )
            _require(
                policy.terminal_transition_receipt_digest == _digest(receipt)
                and policy.unique_result_key
                == _digest(
                    (
                        _digest(receipt),
                        policy.policy_rule_digest,
                    )
                ),
                "reattachment policy result is not uniquely terminal-bound",
            )
            fact = staged_objects.get(receipt.transition_fact_digest)
            installed_entry = staged_objects.get(receipt.installed_keyed_head_digest)
            prior_entry = staged_objects.get(receipt.prior_keyed_head_digest)
            plan = (
                staged_objects.get(prior_entry.boundary_installation_plan_digest)
                if isinstance(prior_entry, ObserverGrantLedgerHead)
                else None
            )
            _require(
                isinstance(fact, ObserverGrantTerminalTransitionFact)
                and isinstance(installed_entry, ObserverGrantLedgerHead)
                and isinstance(prior_entry, ObserverGrantLedgerHead)
                and isinstance(plan, ObserverGrantBoundaryInstallationPlan),
                "server terminal fact, plan, or keyed heads are absent",
            )
            _server_transition_guard(
                kind,
                prior_entry.phase,
                installed_entry.phase,
            )
            _require(
                len(context.deadline_intents) == 1
                and len(context.deadline_conditions) == 1
                and context.deadline_intents[0].purpose
                == EXPIRY_AT_OR_AFTER_EXCLUSIVE_DEADLINE
                and context.deadline_intents[0].deadline_kind
                == "SERVER_GRANT_NOT_AFTER"
                and context.deadline_intents[0].exclusive_deadline
                == prior_entry.effective_server_not_after
                and context.deadline_conditions[0].deadline_predicate_result
                and context.deadline_conditions[0].trusted_commit_time_sample
                >= prior_entry.effective_server_not_after
                and fact.stable_registry_key == prior_entry.registry_key
                and fact.full_boundary_key == prior_entry.full_boundary_key
                and fact.complete_boundary_member_identities
                == tuple(member.identity for member in plan.boundary_members)
                and fact.terminal_reason == "EXPIRED"
                and fact.actor_or_event == "trusted-clock-expiry"
                and fact.authority_clock_incarnation
                == context.commit_clock_incarnation
                == prior_state.coordinator_clock_incarnation
                and fact.reattachment_policy_rule_digest
                == _SERVER_EXPIRY_POLICY_RULE_DIGEST
                and fact.reattachment_policy_inputs_digest
                == _SERVER_EXPIRY_POLICY_INPUTS_DIGEST
                and not fact.boundary_failure_evidence
                and fact.prior_outer_head_digest == _digest(prior_state)
                and fact.prior_registry_head_digest == _digest(prior_registry)
                and installed_entry.terminal_transition_fact_digest == _digest(fact)
                and installed_state.transition_fact_digest == _digest(fact)
                and installed_entry.prior_keyed_head_digest == _digest(prior_entry)
                and installed_entry.registry_key == prior_entry.registry_key
                and installed_entry.full_boundary_key == prior_entry.full_boundary_key
                and policy.installed_terminal_keyed_head_digest
                == _digest(installed_entry)
                and receipt.prior_outer_head_digest == _digest(prior_state)
                and receipt.installed_outer_head_digest == _digest(installed_state)
                and receipt.prior_registry_head_digest == _digest(prior_registry)
                and receipt.installed_registry_head_digest
                == _digest(installed_registry)
                and receipt.prior_keyed_head_digest == _digest(prior_entry)
                and receipt.installed_keyed_head_digest == _digest(installed_entry)
                and receipt.installed_selector_version == context.selector_version
                and receipt.installed_selector_digest == _digest(bundle.selector)
                and receipt.outer_commit_receipt_digest
                == _digest(bundle.generic_commit_payload)
                and receipt.registry_commit_receipt_digest == _digest(registry_receipt)
                and fact.prior_keyed_head_digest == _digest(prior_entry)
                and fact.deadline_intent_digest
                == _intent_set_digest(context.deadline_intents)
                and receipt.deadline_conditions == context.deadline_conditions
                and policy.policy_rule_digest == fact.reattachment_policy_rule_digest
                and policy.policy_inputs_digest
                == fact.reattachment_policy_inputs_digest
                and policy.requester_lineage_digest == _digest(fact.stable_registry_key)
                and policy.terminal_reason == fact.terminal_reason
                and policy.authority_source_receipt_digest
                == _SERVER_EXPIRY_AUTHORITY_SOURCE_RECEIPT_DIGEST
                and policy.outcome == "REATTACH_ALLOWED"
                and policy.installed_selector_version == context.selector_version
                and policy.installed_selector_digest == _digest(bundle.selector)
                and policy.outer_commit_receipt_digest
                == _digest(bundle.generic_commit_payload),
                "server terminal fact/receipt/policy DAG mismatch",
            )
        else:
            raise ProbeError("server transition lacks closed semantic dispatch")
        return

    _require(
        isinstance(installed_state, TrustedDeliveryReleaseStateHead),
        "boundary selector installed a non-boundary state",
    )
    _require(
        isinstance(
            bundle.generic_commit_payload,
            TrustedDeliveryReleaseStateCommitReceipt,
        )
        and isinstance(
            bundle.selector,
            InstalledTrustedDeliveryReleaseSelector,
        ),
        "boundary generic/selector type mismatch",
    )
    _require(
        specialized
        and isinstance(
            specialized[0],
            TrustedDeliveryBoundaryGrantMapCommitReceipt,
        ),
        "boundary transaction lacks exact map commit",
    )
    map_receipt = specialized[0]
    installed_map = staged_objects.get(installed_state.grant_map_head_digest)
    _require(
        isinstance(installed_map, TrustedDeliveryBoundaryGrantMapHead),
        "installed boundary map root is absent",
    )
    prior_map: TrustedDeliveryBoundaryGrantMapHead | None = None
    if prior_state is not None:
        _require(
            isinstance(prior_state, TrustedDeliveryReleaseStateHead),
            "boundary prior state has wrong type",
        )
        prior_map_value = staged_objects.get(prior_state.grant_map_head_digest)
        _require(
            isinstance(prior_map_value, TrustedDeliveryBoundaryGrantMapHead),
            "boundary prior map root is absent",
        )
        prior_map = prior_map_value
    _require(
        map_receipt.installed_map_head_digest == _digest(installed_map)
        and map_receipt.prior_map_head_digest
        == (None if prior_map is None else _digest(prior_map)),
        "boundary map commit roots mismatch",
    )
    _require(
        map_receipt.transition_kind == context.transition_kind,
        "boundary map commit transition mismatch",
    )
    _require(
        installed_state.prior_outer_head_digest
        == (None if prior_state is None else _digest(prior_state))
        and installed_state.state_version
        == (1 if prior_state is None else prior_state.state_version + 1),
        "boundary outer ancestry/version mismatch",
    )
    _require(
        installed_map.prior_map_head_digest
        == (None if prior_map is None else _digest(prior_map))
        and installed_map.state_version
        == (1 if prior_map is None else prior_map.state_version + 1),
        "boundary map ancestry/version mismatch",
    )
    if prior_state is not None:
        _require(
            (
                installed_state.boundary_principal,
                installed_state.boundary_instance,
                installed_state.delivery_domain,
                installed_state.deadline_policy_id,
                installed_state.state_incarnation,
                installed_state.security_state_digest,
                installed_state.current_security_key_id,
                installed_state.boundary_clock_incarnation,
            )
            == (
                prior_state.boundary_principal,
                prior_state.boundary_instance,
                prior_state.delivery_domain,
                prior_state.deadline_policy_id,
                prior_state.state_incarnation,
                prior_state.security_state_digest,
                prior_state.current_security_key_id,
                prior_state.boundary_clock_incarnation,
            ),
            "boundary authority/security/clock identity drift",
        )
    installed_entries = _tuple_map(installed_map.entries)
    prior_entries = {} if prior_map is None else _tuple_map(prior_map.entries)
    _require(
        len(map_receipt.prior_entry_head_digests)
        == len(map_receipt.installed_entry_head_digests),
        "boundary map receipt changed-entry cardinality mismatch",
    )
    changed_pairs: list[
        tuple[
            TrustedDeliveryBoundaryGrantStateHead | None,
            TrustedDeliveryBoundaryGrantStateHead,
        ]
    ] = []
    changed_keys: set[str] = set()
    for prior_token, installed_digest in zip(
        map_receipt.prior_entry_head_digests,
        map_receipt.installed_entry_head_digests,
        strict=True,
    ):
        installed_entry = staged_objects.get(installed_digest)
        _require(
            isinstance(installed_entry, TrustedDeliveryBoundaryGrantStateHead),
            "boundary map receipt installed entry is absent",
        )
        key_digest = _digest(installed_entry.full_boundary_key)
        _require(key_digest not in changed_keys, "boundary key changed twice")
        changed_keys.add(key_digest)
        expected_prior_digest = prior_entries.get(key_digest)
        _require(
            prior_token == (expected_prior_digest or "")
            and installed_entries.get(key_digest) == installed_digest,
            "boundary map receipt keyed predecessor/successor mismatch",
        )
        prior_entry = (
            None
            if expected_prior_digest is None
            else staged_objects.get(expected_prior_digest)
        )
        _require(
            prior_entry is None
            or isinstance(prior_entry, TrustedDeliveryBoundaryGrantStateHead),
            "boundary prior keyed entry is absent",
        )
        _require(
            installed_entry.prior_entry_head_digest == expected_prior_digest
            and installed_entry.state_version
            == (1 if prior_entry is None else prior_entry.state_version + 1),
            "boundary keyed entry ancestry/version mismatch",
        )
        changed_pairs.append((prior_entry, installed_entry))
    expected_entries = dict(prior_entries)
    for _prior_entry, installed_entry in changed_pairs:
        expected_entries[_digest(installed_entry.full_boundary_key)] = _digest(
            installed_entry
        )
    _require(
        installed_entries == expected_entries,
        "boundary map mutation is not the exact declared key set",
    )
    _require(
        map_receipt.sibling_preservation_digest
        == _semantic_digest(
            "ncp.b01.BoundarySiblingPreservation@1",
            tuple(
                sorted(
                    (key, value)
                    for key, value in installed_entries.items()
                    if key not in changed_keys
                )
            ),
        ),
        "boundary sibling-preservation root mismatch",
    )
    for payload in specialized[1:]:
        _payload_type_id, payload_snapshot = _artifact_field_snapshot(payload)
        payload_values = dict(payload_snapshot)
        for field_name, expected in (
            ("signer_principal", context.authority_principal),
            ("signer_key_id", context.signing_key_id),
            ("signer_security_state_digest", context.security_state_digest),
        ):
            if field_name in payload_values:
                _require(
                    payload_values[field_name] == expected,
                    "boundary receipt signer/security currentness mismatch",
                )
    kind = context.transition_kind
    if kind == "RELEASE_STATE_GENESIS_FROM_UNINITIALIZED":
        _require(
            prior_state is None
            and prior_map is None
            and not changed_pairs
            and not installed_entries
            and len(specialized) == 1
            and not bundle.co_committed_objects,
            "boundary genesis shape is not unique",
        )
        allocation = staged_objects.get(installed_state.transition_fact_digest or "")
        _require(
            isinstance(allocation, ParentSelectorAllocationReceipt)
            and installed_map.transition_fact_digest == _digest(allocation)
            and (
                installed_state.next_release_sequence,
                installed_state.next_output_slot,
                installed_state.next_attempt_sequence,
            )
            == (1, 1, 1)
            and not installed_state.outbox_items
            and not installed_state.drain_facts
            and not installed_state.drain_dispositions
            and not installed_state.consumed_read_decision_digests,
            "boundary genesis allocation/counters/partitions mismatch",
        )
    elif kind == "PREPARE_BOUNDARY_GRANT":
        receipt = specialized[1]
        _require(
            isinstance(
                receipt,
                TrustedDeliveryBoundaryGrantEnforcementReceipt,
            ),
            "boundary prepare lacks enforcement receipt",
        )
        fact = staged_objects.get(receipt.preparation_fact_digest)
        _require(len(changed_pairs) == 1, "boundary prepare changes one exact key")
        prior_entry, installed_entry = changed_pairs[0]
        plan = staged_objects.get(fact.boundary_installation_plan_digest)
        grant = staged_objects.get(fact.canonical_grant_digest)
        _require(
            isinstance(fact, TrustedDeliveryBoundaryGrantPreparationFact)
            and isinstance(plan, ObserverGrantBoundaryInstallationPlan)
            and isinstance(grant, ObserverGrant)
            and prior_entry is None
            and fact.deadline_intent_set_digest
            == _intent_set_digest(context.deadline_intents)
            and receipt.installed_entry_head_digest
            in map_receipt.installed_entry_head_digests,
            "boundary prepare fact/receipt DAG mismatch",
        )
        _validate_plan_and_grant(plan, grant, installed_entry.full_boundary_key)
        _boundary_transition_guard(
            kind,
            "ABSENT",
            installed_entry.phase,
        )
        member_index = tuple(plan.boundary_members).index(fact.boundary_member)
        _require(
            fact.boundary_member == installed_entry.boundary_member
            and fact.deadline == plan.boundary_deadlines[member_index]
            and installed_entry.deadline == fact.deadline
            and installed_entry.preparation_fact_digest == _digest(fact)
            and installed_state.transition_fact_digest == _digest(fact)
            and installed_map.transition_fact_digest == _digest(fact)
            and receipt.canonical_grant_digest == _digest(grant)
            and receipt.boundary_installation_plan_digest == _digest(plan),
            "boundary prepare member/deadline/successor links mismatch",
        )
        server_snapshots = tuple(
            item
            for item in staged_objects.values()
            if isinstance(item, ImmutableAuthoritySnapshot)
            and item.store_id == "observer-authorization-server"
            and item.state_digest == fact.server_pending_outer_head_digest
        )
        _require(
            len(server_snapshots) == 1,
            "boundary prepare lacks the exact selected server snapshot",
        )
        server_snapshot = server_snapshots[0]
        _validate_atomic_snapshot(server_snapshot)
        server_objects = _tuple_map(server_snapshot.objects)
        server_signed = _tuple_map(server_snapshot.signed_bytes)
        _require(
            server_snapshot.snapshot_version == fact.server_selector_version
            and fact.server_outer_commit_receipt_digest in server_signed
            and fact.server_registry_commit_receipt_digest in server_signed
            and server_objects.get(fact.server_pending_keyed_head_digest) is not None,
            "boundary prepare server pending authority links mismatch",
        )
    elif kind == "ACTIVATE_PREPARED_BOUNDARY_GRANT":
        receipt = specialized[1]
        _require(
            isinstance(
                receipt,
                TrustedDeliveryBoundaryGrantActivationReceipt,
            ),
            "boundary activation lacks activation receipt",
        )
        fact = staged_objects.get(receipt.activation_fact_digest)
        _require(
            isinstance(fact, TrustedDeliveryBoundaryGrantActivationFact)
            and fact.deadline_intent_set_digest
            == _intent_set_digest(context.deadline_intents),
            "boundary activation fact/intent DAG mismatch",
        )
        _require(len(changed_pairs) == 1, "boundary activation changes one key")
        prior_entry, installed_entry = changed_pairs[0]
        _require(
            prior_entry is not None,
            "boundary activation lacks its prepared predecessor",
        )
        _boundary_transition_guard(
            kind,
            prior_entry.phase,
            installed_entry.phase,
        )
        _require(
            fact.prior_entry_head_digest == _digest(prior_entry)
            and installed_entry.activation_fact_digest == _digest(fact)
            and installed_entry.installed_activation_set_receipt_digest
            == fact.server_activation_set_receipt_digest
            and installed_entry.installed_activation_entry_proof_digest
            == fact.server_activation_entry_proof_digest
            and receipt.installed_entry_head_digest == _digest(installed_entry)
            and installed_state.transition_fact_digest == _digest(fact),
            "boundary activation predecessor/server-decision/successor links mismatch",
        )
        server_snapshots = tuple(
            item
            for item in staged_objects.values()
            if type(item) is ImmutableAuthoritySnapshot
            and item.store_id == "observer-authorization-server"
            and item.snapshot_version == fact.server_selector_version
            and _authority_snapshot_persistence_root(
                item,
                validation_complete=True,
            )
            == fact.server_snapshot_persistence_root
            and fact.server_activation_set_receipt_digest in _tuple_map(item.objects)
        )
        _require(
            len(server_snapshots) == 1,
            "boundary activation lacks the exact live server snapshot",
        )
        server_snapshot = server_snapshots[0]
        _validate_atomic_snapshot(server_snapshot)
        server_objects = _tuple_map(server_snapshot.objects)
        selected_server_transitions = tuple(
            transition
            for transition in server_snapshot.transitions
            if transition.transition_kind == "ACTIVATE_PENDING_GRANT"
            and transition.installed_state_digest == server_snapshot.state_digest
            and transition.selector_version == fact.server_selector_version
            and transition.selector_digest == fact.server_selector_digest
            and fact.server_activation_set_receipt_digest
            in transition.specialized_receipt_digests
            and fact.server_activation_entry_proof_digest
            in transition.specialized_receipt_digests
        )
        set_receipt = server_objects.get(fact.server_activation_set_receipt_digest)
        proof = server_objects.get(fact.server_activation_entry_proof_digest)
        enforcement_receipts = tuple(
            item
            for item in staged_objects.values()
            if isinstance(
                item,
                TrustedDeliveryBoundaryGrantEnforcementReceipt,
            )
            and item.installed_entry_head_digest == _digest(prior_entry)
        )
        _require(
            isinstance(
                set_receipt,
                ObserverGrantBoundaryInstallationSetReceipt,
            )
            and isinstance(proof, ObserverGrantRegistryActivationEntryProof)
            and len(selected_server_transitions) == 1
            and len(enforcement_receipts) == 1
            and proof.full_boundary_key == installed_entry.full_boundary_key
            and (
                installed_entry.boundary_member.identity,
                _digest(enforcement_receipts[0]),
            )
            in set_receipt.canonical_prepared_member_receipts,
            "boundary activation server set/proof omits its exact preparation",
        )
    elif kind == "CREATE_TRUSTED_DELIVERY_RELEASE_RESERVATION":
        _require(
            len(changed_pairs) == 1 and len(specialized) == 1,
            "reservation changes one key and has no opaque receipt",
        )
        prior_entry, installed_entry = changed_pairs[0]
        reservation = staged_objects.get(installed_state.transition_fact_digest or "")
        _require(
            isinstance(prior_entry, TrustedDeliveryBoundaryGrantStateHead)
            and isinstance(reservation, TrustedDeliveryReleaseReservation)
            and prior_entry.phase == "LIVE_BOUNDARY_GRANT"
            and installed_entry.phase == prior_entry.phase
            and reservation.full_boundary_key == installed_entry.full_boundary_key
            and _digest(reservation) in installed_entry.pending_reservation_digests
            and _digest(reservation) not in prior_entry.pending_reservation_digests,
            "reservation is not one exact LIVE-key allocation",
        )
        preparation_fact = staged_objects.get(prior_entry.preparation_fact_digest)
        _require(
            isinstance(
                preparation_fact,
                TrustedDeliveryBoundaryGrantPreparationFact,
            ),
            "reservation preparation fact is absent",
        )
        plan = staged_objects.get(preparation_fact.boundary_installation_plan_digest)
        matching_read_scopes = tuple(
            value
            for value in staged_objects.values()
            if type(value) is CanonicalObserverReadScope
            and value.scope_digest == reservation.canonical_scope_digest
        )
        matching_memberships = tuple(
            value
            for value in staged_objects.values()
            if type(value) is ObserverBoundaryReadScopeMembership
            and value.membership_digest == reservation.boundary_scope_membership_digest
        )
        read_scope = matching_read_scopes[0] if len(matching_read_scopes) == 1 else None
        membership = matching_memberships[0] if len(matching_memberships) == 1 else None
        read_decision = staged_objects.get(
            reservation.read_authorization_decision_digest
        )
        retained_cuts = tuple(
            value
            for value in staged_objects.values()
            if type(value) is ExpectedObserverReadAuthorizationCut
        )
        retained_cut = retained_cuts[0] if len(retained_cuts) == 1 else None
        activation_receipts = tuple(
            value
            for value in staged_objects.values()
            if type(value) is TrustedDeliveryBoundaryGrantActivationReceipt
            and value.installed_entry_head_digest == _digest(prior_entry)
        )
        activation_receipt = (
            activation_receipts[0] if len(activation_receipts) == 1 else None
        )
        expected_grant_currentness_state_cut = ExpectedGrantCurrentnessStateCut(
            boundary_state_head_digest=_digest(prior_state),
            grant_entry_head_digest=_digest(prior_entry),
            state_version=prior_state.state_version,
            prior_release_count=(
                prior_state.consumed_read_decision_digests.count(
                    reservation.read_authorization_decision_digest
                )
            ),
            grant_currentness_receipt_digest=_digest(activation_receipt),
            local_grant_exclusive_not_after=(
                prior_entry.deadline.boundary_release_not_after
            ),
            evidence_artifact_digest=grant_currentness_artifact_digest(
                reservation.grant_currentness_evidence
            ),
        )
        try:
            validate_release_cas(
                reservation.release_cas,
                scope=read_scope,
                membership=membership,
                decision=read_decision,
                release_context=reservation.release_recipient_context,
                qualified_deadline_mapping=(reservation.qualified_deadline_mapping),
                grant_currentness_evidence=(reservation.grant_currentness_evidence),
                expected_observer_identity=(
                    reservation.full_boundary_key.registry_key.requester_principal,
                    reservation.release_recipient_context.recipient_instance,
                ),
                expected_boundary_identity=(
                    installed_entry.boundary_member.boundary_principal,
                    installed_entry.boundary_member.boundary_instance,
                    installed_entry.boundary_member.deadline_policy_id,
                ),
                expected_authorization_audience=read_scope.authorization_audience,
                expected_authorization_cut=retained_cut,
                expected_issuer_identity=(
                    SERVER_PRINCIPAL,
                    SERVER_KEY_ID,
                    SERVER_STATE_INCARNATION,
                ),
                expected_release_recipient_identity=(
                    reservation.full_boundary_key.registry_key.requester_principal,
                    reservation.release_recipient_context.recipient_instance,
                ),
                expected_release_transport_context=(
                    reservation.expected_release_transport_context
                ),
                expected_local_security_state=(
                    installed_entry.boundary_member.security_state_digest,
                    plan.security_epoch,
                    plan.revocation_epoch,
                ),
                expected_release_context_artifact_digest=(
                    release_recipient_artifact_digest(
                        reservation.release_recipient_context
                    )
                ),
                expected_grant_currentness_state_cut=(
                    expected_grant_currentness_state_cut
                ),
                expected_deadline_mapping_state_cut=(
                    reservation.expected_deadline_mapping_state_cut
                ),
                release_idempotency_key=(
                    reservation.release_cas.release_idempotency_key
                ),
                expected_boundary_clock_incarnation=(
                    installed_entry.boundary_member.clock_mapping.boundary_clock_incarnation
                ),
                expected_mapping_policy_artifact_digest=_digest(
                    installed_entry.boundary_member.clock_mapping
                ),
                checked_at=context.exact_commit_time,
                fixture_key=_READ_DECISION_SEAL_KEY,
            )
        except (BridgeValidationError, TypeError) as exc:
            raise ProbeError("reservation read-decision/CAS chain is invalid") from exc
        _require(
            isinstance(plan, ObserverGrantBoundaryInstallationPlan)
            and type(read_scope) is CanonicalObserverReadScope
            and type(membership) is ObserverBoundaryReadScopeMembership
            and type(read_decision) is SealedObserverReadAuthorizationDecision
            and reservation.retained_authorization_cut == retained_cut
            and reservation.expected_grant_currentness_state_cut
            == expected_grant_currentness_state_cut
            and read_scope == installed_entry.boundary_member.read_scope
            and membership == installed_entry.boundary_member.scope_membership
            and reservation.canonical_scope_digest in plan.exact_scope_digests
            and read_decision.full_boundary_key_digest
            == _digest(reservation.full_boundary_key)
            and read_decision.grant_digest
            == reservation.full_boundary_key.canonical_grant_digest
            and reservation.read_authorization_decision_digest
            not in prior_state.consumed_read_decision_digests
            and installed_state.consumed_read_decision_digests
            == prior_state.consumed_read_decision_digests
            and installed_state.next_release_sequence
            == prior_state.next_release_sequence
            and installed_state.next_output_slot == prior_state.next_output_slot
            and installed_state.used_release_identities
            == prior_state.used_release_identities
            and installed_state.used_output_slots == prior_state.used_output_slots
            and installed_state.installed_release_counter_state_digests
            == prior_state.installed_release_counter_state_digests
            and installed_entry.installed_release_counter_state_digest
            == prior_entry.installed_release_counter_state_digest
            and reservation.release_sequence == prior_state.next_release_sequence
            and reservation.output_slot == prior_state.next_output_slot,
            "reservation changed authority, quota, allocator, or output state "
            "instead of installing only its exclusive pending-intent fence",
        )
    elif kind == "COMMIT_TRUSTED_DELIVERY_RELEASE_OUTBOX":
        _require(
            len(changed_pairs) == 1
            and len(specialized) == 2
            and len(bundle.co_committed_objects) == 1,
            "outbox commit lacks its exact key/receipt/item shape",
        )
        prior_entry, installed_entry = changed_pairs[0]
        receipt = specialized[1]
        outbox = bundle.co_committed_objects[0]
        commitment = staged_objects.get(receipt.outbox_commitment_digest)
        pending_reservation = staged_objects.get(
            commitment.reservation_digest
            if isinstance(commitment, TrustedDeliveryReleaseOutboxCommitment)
            else ""
        )
        reservation = staged_objects.get(
            commitment.validated_release_reservation_digest
            if isinstance(commitment, TrustedDeliveryReleaseOutboxCommitment)
            else ""
        )
        _require(
            isinstance(prior_entry, TrustedDeliveryBoundaryGrantStateHead)
            and isinstance(receipt, TrustedDeliveryReleaseReceipt)
            and isinstance(commitment, TrustedDeliveryReleaseOutboxCommitment)
            and isinstance(
                pending_reservation,
                TrustedDeliveryReleaseReservation,
            )
            and isinstance(reservation, TrustedDeliveryReleaseReservation)
            and isinstance(outbox, TrustedDeliveryReleaseOutbox),
            "outbox commit DAG object is absent",
        )
        preparation_fact = staged_objects.get(prior_entry.preparation_fact_digest)
        plan = staged_objects.get(
            preparation_fact.boundary_installation_plan_digest
            if isinstance(
                preparation_fact,
                TrustedDeliveryBoundaryGrantPreparationFact,
            )
            else ""
        )
        read_decision = staged_objects.get(
            reservation.read_authorization_decision_digest
        )
        activation_receipt = staged_objects.get(reservation.activation_receipt_digest)
        activation_fact = staged_objects.get(
            activation_receipt.activation_fact_digest
            if isinstance(
                activation_receipt,
                TrustedDeliveryBoundaryGrantActivationReceipt,
            )
            else ""
        )
        enforcement_receipts = tuple(
            value
            for value in staged_objects.values()
            if isinstance(
                value,
                TrustedDeliveryBoundaryGrantEnforcementReceipt,
            )
            and isinstance(
                activation_receipt,
                TrustedDeliveryBoundaryGrantActivationReceipt,
            )
            and value.installed_entry_head_digest
            == activation_receipt.prior_entry_head_digest
            and value.preparation_fact_digest == prior_entry.preparation_fact_digest
        )
        enforcement_receipt = (
            enforcement_receipts[0] if len(enforcement_receipts) == 1 else None
        )
        expected_grant_currentness_state_cut = ExpectedGrantCurrentnessStateCut(
            boundary_state_head_digest=_digest(prior_state),
            grant_entry_head_digest=_digest(prior_entry),
            state_version=prior_state.state_version,
            prior_release_count=(
                prior_state.consumed_read_decision_digests.count(
                    reservation.read_authorization_decision_digest
                )
            ),
            grant_currentness_receipt_digest=_digest(activation_receipt),
            local_grant_exclusive_not_after=(
                prior_entry.deadline.boundary_release_not_after
            ),
            evidence_artifact_digest=grant_currentness_artifact_digest(
                reservation.grant_currentness_evidence
            ),
        )
        try:
            validate_release_cas(
                reservation.release_cas,
                scope=installed_entry.boundary_member.read_scope,
                membership=installed_entry.boundary_member.scope_membership,
                decision=read_decision,
                release_context=reservation.release_recipient_context,
                qualified_deadline_mapping=(reservation.qualified_deadline_mapping),
                grant_currentness_evidence=(reservation.grant_currentness_evidence),
                expected_observer_identity=(
                    reservation.requester_principal,
                    reservation.release_recipient_context.recipient_instance,
                ),
                expected_boundary_identity=(
                    installed_entry.boundary_member.boundary_principal,
                    installed_entry.boundary_member.boundary_instance,
                    installed_entry.boundary_member.deadline_policy_id,
                ),
                expected_authorization_audience=(
                    installed_entry.boundary_member.read_scope.authorization_audience
                ),
                expected_authorization_cut=(reservation.retained_authorization_cut),
                expected_issuer_identity=(
                    SERVER_PRINCIPAL,
                    SERVER_KEY_ID,
                    SERVER_STATE_INCARNATION,
                ),
                expected_release_recipient_identity=(
                    reservation.requester_principal,
                    reservation.release_recipient_context.recipient_instance,
                ),
                expected_release_transport_context=(
                    reservation.expected_release_transport_context
                ),
                expected_local_security_state=(
                    installed_entry.boundary_member.security_state_digest,
                    plan.security_epoch,
                    plan.revocation_epoch,
                ),
                expected_release_context_artifact_digest=(
                    release_recipient_artifact_digest(
                        reservation.release_recipient_context
                    )
                ),
                expected_grant_currentness_state_cut=(
                    expected_grant_currentness_state_cut
                ),
                expected_deadline_mapping_state_cut=(
                    reservation.expected_deadline_mapping_state_cut
                ),
                release_idempotency_key=(
                    reservation.release_cas.release_idempotency_key
                ),
                expected_boundary_clock_incarnation=(
                    installed_entry.boundary_member.clock_mapping.boundary_clock_incarnation
                ),
                expected_mapping_policy_artifact_digest=_digest(
                    installed_entry.boundary_member.clock_mapping
                ),
                checked_at=context.exact_commit_time,
                fixture_key=_READ_DECISION_SEAL_KEY,
            )
        except (AttributeError, BridgeValidationError, TypeError) as exc:
            raise ProbeError(
                "atomic outbox commit release authority is stale or invalid"
            ) from exc
        _require(
            isinstance(plan, ObserverGrantBoundaryInstallationPlan)
            and isinstance(
                activation_receipt,
                TrustedDeliveryBoundaryGrantActivationReceipt,
            )
            and isinstance(
                activation_fact,
                TrustedDeliveryBoundaryGrantActivationFact,
            )
            and isinstance(
                enforcement_receipt,
                TrustedDeliveryBoundaryGrantEnforcementReceipt,
            )
            and isinstance(
                read_decision,
                SealedObserverReadAuthorizationDecision,
            )
            and activation_receipt.activation_fact_digest
            == prior_entry.activation_fact_digest
            == _digest(activation_fact)
            and prior_entry.prior_entry_head_digest
            == activation_receipt.installed_entry_head_digest
            and activation_fact.prior_entry_head_digest
            == activation_receipt.prior_entry_head_digest
            == enforcement_receipt.installed_entry_head_digest
            and enforcement_receipt.preparation_fact_digest
            == prior_entry.preparation_fact_digest
            and receipt.activation_receipt_digest
            == reservation.activation_receipt_digest
            == _digest(activation_receipt)
            and receipt.enforcement_receipt_digest == _digest(enforcement_receipt)
            and reservation.expected_grant_currentness_state_cut
            == expected_grant_currentness_state_cut
            and reservation.grant_currentness_evidence.boundary_state_head_digest
            == _digest(prior_state)
            and reservation.grant_currentness_evidence.grant_entry_head_digest
            == _digest(prior_entry)
            and (
                pending_reservation.grant_currentness_evidence.boundary_state_head_digest
                != reservation.grant_currentness_evidence.boundary_state_head_digest
            )
            and reservation.validated_release_cas_receipt.release_cas_artifact_digest
            == reservation.release_cas.cas_digest,
            "outbox commit did not refresh currentness, CAS, and validation "
            "against the exact post-reservation state cut",
        )
        try:
            validate_committed_outbox_artifact(
                outbox.committed_bridge_outbox_artifact,
                scope=installed_entry.boundary_member.read_scope,
                membership=installed_entry.boundary_member.scope_membership,
                release_cas=reservation.release_cas,
                validated_release_cas_receipt=(
                    reservation.validated_release_cas_receipt
                ),
                commit_receipt=outbox.bridge_commit_receipt,
                expected_commit_state_cut=(outbox.expected_bridge_commit_state_cut),
                release_context=reservation.release_recipient_context,
                expected_boundary_identity=(
                    installed_entry.boundary_member.boundary_principal,
                    installed_entry.boundary_member.boundary_instance,
                    installed_entry.boundary_member.deadline_policy_id,
                ),
                expected_recipient_identity=(
                    reservation.requester_principal,
                    reservation.release_recipient_context.recipient_instance,
                ),
                expected_boundary_clock_incarnation=(
                    installed_entry.boundary_member.clock_mapping.boundary_clock_incarnation
                ),
                expected_stable_outbox_item_id=outbox.stable_item_id,
                expected_exact_payload=outbox.complete_payload,
                expected_transport_idempotency_key=outbox.idempotency_key,
                expected_artifact_digest=(
                    committed_outbox_artifact_digest(
                        outbox.committed_bridge_outbox_artifact
                    )
                ),
                checked_at=context.exact_commit_time,
                fixture_key=_READ_DECISION_SEAL_KEY,
            )
        except (AttributeError, BridgeValidationError, TypeError) as exc:
            raise ProbeError("committed bridge outbox artifact is invalid") from exc
        _require(
            prior_entry.phase == "LIVE_BOUNDARY_GRANT"
            and installed_entry.phase == prior_entry.phase
            and _digest(pending_reservation) in prior_entry.pending_reservation_digests
            and _digest(pending_reservation)
            not in installed_entry.pending_reservation_digests
            and commitment.reservation_digest == _digest(pending_reservation)
            and commitment.validated_release_reservation_digest == _digest(reservation)
            and reservation.release_sequence == prior_state.next_release_sequence
            and reservation.output_slot == prior_state.next_output_slot
            and reservation.read_authorization_decision_digest
            not in prior_state.consumed_read_decision_digests
            and installed_state.consumed_read_decision_digests
            == tuple(
                sorted(
                    (
                        *prior_state.consumed_read_decision_digests,
                        reservation.read_authorization_decision_digest,
                    )
                )
            )
            and installed_state.next_release_sequence
            == prior_state.next_release_sequence + 1
            and installed_state.next_output_slot == prior_state.next_output_slot + 1
            and installed_state.used_release_identities
            == (
                *prior_state.used_release_identities,
                _uuid_for(
                    (
                        "release",
                        installed_entry.boundary_member.identity,
                        reservation.release_cas.release_idempotency_key,
                        reservation.release_sequence,
                    )
                ),
            )
            and installed_state.used_output_slots
            == (*prior_state.used_output_slots, reservation.output_slot)
            and _tuple_map(installed_state.installed_release_counter_state_digests).get(
                reservation.read_authorization_decision_digest
            )
            == reservation.release_cas.next_release_counter_state_digest
            and installed_entry.installed_release_counter_state_digest
            == reservation.release_cas.next_release_counter_state_digest
            == (
                outbox.committed_bridge_outbox_artifact.installed_release_counter_state_digest
            )
            and _digest(commitment)
            in installed_entry.released_outbox_commitment_digests
            and _tuple_map(installed_state.outbox_items).get(outbox.stable_item_id)
            == _digest(commitment)
            and outbox.release_receipt_digest == _digest(receipt)
            and (
                receipt.bridge_validated_release_cas_receipt_artifact_digest,
                receipt.bridge_commit_receipt_artifact_digest,
                receipt.bridge_prior_storage_state_head_digest,
                receipt.bridge_installed_storage_state_head_digest,
            )
            == (
                outbox.expected_bridge_commit_state_cut.validated_release_cas_receipt_artifact_digest,
                outbox.expected_bridge_commit_state_cut.commit_receipt_artifact_digest,
                outbox.expected_bridge_commit_state_cut.prior_storage_state_head_digest,
                outbox.expected_bridge_commit_state_cut.installed_storage_state_head_digest,
            )
            and receipt.bridge_prior_storage_state_head_digest
            == receipt.prior_outer_head_digest
            and outbox.outbox_commitment_digest == _digest(commitment)
            and outbox.full_boundary_key == commitment.full_boundary_key
            and outbox.payload_digest
            == hashlib.sha256(outbox.complete_payload).hexdigest()
            and outbox.payload_length == len(outbox.complete_payload)
            and outbox.committed_bridge_outbox_artifact.committed_at
            == context.exact_commit_time
            and (
                reservation.canonical_scope_digest,
                reservation.boundary_scope_membership_digest,
                reservation.read_authorization_decision_digest,
                reservation.release_authority_recheck_digest,
            )
            == (
                commitment.canonical_scope_digest,
                commitment.boundary_scope_membership_digest,
                commitment.read_authorization_decision_digest,
                commitment.release_authority_recheck_digest,
            )
            == (
                receipt.canonical_scope_digest,
                receipt.boundary_scope_membership_digest,
                receipt.read_authorization_decision_digest,
                receipt.release_authority_recheck_digest,
            )
            == (
                outbox.canonical_scope_digest,
                outbox.boundary_scope_membership_digest,
                outbox.read_authorization_decision_digest,
                outbox.release_authority_recheck_digest,
            )
            and (
                outbox.payload_digest,
                outbox.payload_length,
                outbox.output_slot,
                outbox.idempotency_key,
                outbox.attempt_namespace,
            )
            == (
                commitment.payload_digest,
                commitment.payload_length,
                commitment.output_slot,
                commitment.idempotency_key,
                commitment.attempt_namespace,
            ),
            "outbox commitment/receipt/item/successor DAG mismatch",
        )
    elif kind == "START_EXTERNAL_TRANSPORT_DRAIN":
        _require(
            len(changed_pairs) == 1 and len(specialized) == 1,
            "drain start changes one key and has no opaque receipt",
        )
        prior_entry, installed_entry = changed_pairs[0]
        fact = staged_objects.get(installed_state.transition_fact_digest or "")
        outbox = (
            staged_objects.get(fact.exact_outbox_item_digest)
            if isinstance(fact, TrustedDeliveryExternalTransportDrainFact)
            else None
        )
        commitment = (
            staged_objects.get(outbox.outbox_commitment_digest)
            if isinstance(outbox, TrustedDeliveryReleaseOutbox)
            else None
        )
        reservation = (
            staged_objects.get(commitment.validated_release_reservation_digest)
            if isinstance(commitment, TrustedDeliveryReleaseOutboxCommitment)
            else None
        )
        try:
            validate_dispatch_context(
                fact.dispatch_context,
                scope=installed_entry.boundary_member.read_scope,
                membership=installed_entry.boundary_member.scope_membership,
                release_context=reservation.release_recipient_context,
                release_cas=reservation.release_cas,
                validated_release_cas_receipt=(
                    reservation.validated_release_cas_receipt
                ),
                committed_outbox=(outbox.committed_bridge_outbox_artifact),
                commit_receipt=outbox.bridge_commit_receipt,
                expected_commit_state_cut=(outbox.expected_bridge_commit_state_cut),
                expected_boundary_identity=(
                    installed_entry.boundary_member.boundary_principal,
                    installed_entry.boundary_member.boundary_instance,
                    installed_entry.boundary_member.deadline_policy_id,
                ),
                expected_recipient_identity=(
                    reservation.requester_principal,
                    reservation.release_recipient_context.recipient_instance,
                ),
                expected_release_transport_context=(
                    reservation.expected_release_transport_context
                ),
                expected_release_security_state=(
                    installed_entry.boundary_member.security_state_digest,
                    reservation.release_recipient_context.local_security_epoch,
                    reservation.release_recipient_context.local_revocation_epoch,
                ),
                expected_boundary_clock_incarnation=(
                    installed_entry.boundary_member.clock_mapping.boundary_clock_incarnation
                ),
                expected_release_context_artifact_digest=(
                    release_recipient_artifact_digest(
                        reservation.release_recipient_context
                    )
                ),
                release_context_checked_at=(
                    reservation.release_recipient_context.verified_at
                ),
                expected_stable_outbox_item_id=outbox.stable_item_id,
                actual_dispatch_payload=fact.actual_dispatch_payload,
                expected_committed_outbox_artifact_digest=(
                    committed_outbox_artifact_digest(
                        outbox.committed_bridge_outbox_artifact
                    )
                ),
                expected_dispatch_attempt_id=fact.attempt_identity,
                expected_transport_idempotency_key=fact.idempotency_key,
                expected_local_security_state=(
                    installed_entry.boundary_member.security_state_digest,
                    reservation.release_recipient_context.local_security_epoch,
                    reservation.release_recipient_context.local_revocation_epoch,
                ),
                expected_destination_cut=(fact.expected_dispatch_destination_cut),
                expected_dispatch_context_artifact_digest=(
                    fact.dispatch_context_artifact_digest
                ),
                checked_at=context.exact_commit_time,
                fixture_key=_READ_DECISION_SEAL_KEY,
            )
        except (AttributeError, BridgeValidationError, TypeError) as exc:
            raise ProbeError("drain dispatch context is invalid") from exc
        prior_dispositions = sorted(
            (
                staged_objects[digest]
                for _identity, digest in prior_state.drain_dispositions
                if isinstance(
                    staged_objects.get(digest),
                    TrustedDeliveryExternalTransportDisposition,
                )
                and staged_objects[digest].stable_item_id == fact.stable_item_id
            ),
            key=lambda item: item.attempt_sequence,
        )
        if not prior_dispositions:
            retry_proof_valid = (
                fact.receiver_dedup_retry_proof_digest is None
                and fact.attempt_sequence == 1
            )
        else:
            prior_disposition = prior_dispositions[-1]
            prior_fact = staged_objects.get(prior_disposition.drain_fact_digest)
            retry_proof = staged_objects.get(
                fact.receiver_dedup_retry_proof_digest or ""
            )
            try:
                validate_receiver_deduplication_retry_proof(
                    retry_proof,
                    outbox=outbox,
                    prior_fact=prior_fact,
                    prior_disposition=prior_disposition,
                    expected_destination_cut=(fact.expected_dispatch_destination_cut),
                )
            except (AttributeError, ProbeError, TypeError):
                retry_proof_valid = False
            else:
                retry_proof_valid = (
                    fact.attempt_sequence == prior_disposition.attempt_sequence + 1
                )
        terminal_dispatch_authorized = True
        if (
            isinstance(
                prior_entry,
                TrustedDeliveryBoundaryGrantStateHead,
            )
            and prior_entry.phase == "TERMINAL_BOUNDARY_GRANT"
        ):
            terminal_fact = staged_objects.get(prior_entry.terminal_fact_digest or "")
            terminal_dispatch_authorized = (
                isinstance(
                    terminal_fact,
                    TrustedDeliveryBoundaryTerminalTransitionFact,
                )
                and terminal_fact.full_boundary_key == prior_entry.full_boundary_key
                and terminal_fact.prior_entry_head_digest
                == prior_entry.prior_entry_head_digest
                and terminal_fact.cause in {"SERVER_TERMINAL", "SERVER_RENEWAL_FENCE"}
                and isinstance(
                    commitment,
                    TrustedDeliveryReleaseOutboxCommitment,
                )
                and _digest(commitment) in terminal_fact.retained_outbox_item_digests
            )
        _require(
            isinstance(prior_entry, TrustedDeliveryBoundaryGrantStateHead)
            and isinstance(fact, TrustedDeliveryExternalTransportDrainFact)
            and isinstance(outbox, TrustedDeliveryReleaseOutbox)
            and prior_entry.phase in {"LIVE_BOUNDARY_GRANT", "TERMINAL_BOUNDARY_GRANT"}
            and installed_entry.phase == prior_entry.phase
            and fact.full_boundary_key == installed_entry.full_boundary_key
            and terminal_dispatch_authorized
            and fact.stable_item_id == outbox.stable_item_id
            and fact.idempotency_key == outbox.idempotency_key
            and fact.actual_dispatch_payload == outbox.complete_payload
            and fact.dispatch_context_artifact_digest
            == dispatch_artifact_digest(fact.dispatch_context)
            and (
                fact.canonical_scope_digest,
                fact.boundary_scope_membership_digest,
                fact.read_authorization_decision_digest,
                fact.release_authority_recheck_digest,
            )
            == (
                outbox.canonical_scope_digest,
                outbox.boundary_scope_membership_digest,
                outbox.read_authorization_decision_digest,
                outbox.release_authority_recheck_digest,
            )
            and retry_proof_valid
            and _tuple_map(prior_state.outbox_items).get(fact.stable_item_id)
            == outbox.outbox_commitment_digest
            and _tuple_map(installed_state.drain_facts).get(fact.attempt_identity)
            == _digest(fact)
            and _digest(fact) in installed_entry.active_drain_fact_digests,
            "drain start is not over the exact retained outbox item",
        )
    elif kind == "RESOLVE_EXTERNAL_TRANSPORT_DRAIN":
        _require(
            len(changed_pairs) == 1 and len(specialized) == 1,
            "drain resolution changes one key and has no opaque receipt",
        )
        prior_entry, installed_entry = changed_pairs[0]
        disposition = staged_objects.get(installed_state.transition_fact_digest or "")
        fact = (
            staged_objects.get(disposition.drain_fact_digest)
            if isinstance(
                disposition,
                TrustedDeliveryExternalTransportDisposition,
            )
            else None
        )
        transport_evidence_valid = False
        if isinstance(
            disposition, TrustedDeliveryExternalTransportDisposition
        ) and isinstance(fact, TrustedDeliveryExternalTransportDrainFact):
            if disposition.outcome == "AMBIGUOUS_AFTER_EXTERNAL_TRANSPORT":
                transport_evidence_valid = (
                    disposition.authenticated_transport_evidence_digest is None
                )
            elif disposition.outcome in {"DELIVERED", "REJECTED"}:
                transport_evidence = staged_objects.get(
                    disposition.authenticated_transport_evidence_digest or ""
                )
                try:
                    validate_transport_disposition_evidence(
                        transport_evidence,
                        fact=fact,
                        outcome=disposition.outcome,
                        commit_time=context.exact_commit_time,
                        commit_clock_incarnation=context.commit_clock_incarnation,
                    )
                except (AttributeError, ProbeError, TypeError):
                    transport_evidence_valid = False
                else:
                    transport_evidence_valid = True
        _require(
            isinstance(prior_entry, TrustedDeliveryBoundaryGrantStateHead)
            and isinstance(
                disposition,
                TrustedDeliveryExternalTransportDisposition,
            )
            and isinstance(fact, TrustedDeliveryExternalTransportDrainFact)
            and disposition.dispatch_context_artifact_digest
            == fact.dispatch_context_artifact_digest
            and _digest(fact) in prior_entry.active_drain_fact_digests
            and _digest(fact) not in installed_entry.active_drain_fact_digests
            and _digest(disposition) in installed_entry.terminal_disposition_digests
            and fact.attempt_identity not in _tuple_map(installed_state.drain_facts)
            and _tuple_map(installed_state.drain_dispositions).get(
                fact.attempt_identity
            )
            == _digest(disposition)
            and (
                disposition.canonical_scope_digest,
                disposition.boundary_scope_membership_digest,
                disposition.read_authorization_decision_digest,
                disposition.release_authority_recheck_digest,
            )
            == (
                fact.canonical_scope_digest,
                fact.boundary_scope_membership_digest,
                fact.read_authorization_decision_digest,
                fact.release_authority_recheck_digest,
            )
            and disposition.outcome
            in {
                "DELIVERED",
                "REJECTED",
                "AMBIGUOUS_AFTER_EXTERNAL_TRANSPORT",
            }
            and transport_evidence_valid
            and disposition.no_resend_right
            == (disposition.outcome in {"DELIVERED", "REJECTED"}),
            "drain resolution does not consume one exact active attempt",
        )
    elif kind == "TERMINATE_BOUNDARY_GRANT":
        _require(
            len(changed_pairs) == 1 and len(specialized) == 2,
            "boundary terminal transition changes one key with one receipt",
        )
        prior_entry, installed_entry = changed_pairs[0]
        receipt = specialized[1]
        fact = staged_objects.get(receipt.terminal_fact_digest)
        _require(
            isinstance(prior_entry, TrustedDeliveryBoundaryGrantStateHead)
            and isinstance(
                receipt,
                TrustedDeliveryBoundaryTerminalInstallationReceipt,
            )
            and isinstance(fact, TrustedDeliveryBoundaryTerminalTransitionFact),
            "boundary terminal fact/receipt/predecessor is absent",
        )
        _boundary_transition_guard(
            kind,
            prior_entry.phase,
            installed_entry.phase,
        )
        _require(
            fact.operation_id == context.operation_id
            and fact.full_boundary_key
            == prior_entry.full_boundary_key
            == installed_entry.full_boundary_key
            and fact.prior_outer_head_digest == _digest(prior_state)
            and fact.prior_map_head_digest == _digest(prior_map)
            and fact.prior_entry_head_digest == _digest(prior_entry)
            and fact.deadline == prior_entry.deadline
            and installed_entry.terminal_fact_digest == _digest(fact)
            and installed_state.transition_fact_digest == _digest(fact)
            and receipt.installed_entry_head_digest == _digest(installed_entry)
            and receipt.full_boundary_key == fact.full_boundary_key
            and receipt.prior_outer_head_digest == _digest(prior_state)
            and receipt.installed_outer_head_digest == _digest(installed_state)
            and receipt.prior_map_head_digest == _digest(prior_map)
            and receipt.installed_map_head_digest == _digest(installed_map)
            and receipt.prior_entry_head_digest == _digest(prior_entry)
            and receipt.installed_selector_version == context.selector_version
            and receipt.installed_selector_digest == _digest(bundle.selector)
            and receipt.outer_commit_receipt_digest
            == _digest(bundle.generic_commit_payload)
            and receipt.map_commit_receipt_digest == _digest(map_receipt)
            and fact.canceled_reservation_digests
            == prior_entry.pending_reservation_digests
            and fact.canceled_pre_release_commitment_digests
            == prior_entry.pre_release_commitment_digests
            and not installed_entry.pending_reservation_digests
            and not installed_entry.pre_release_commitment_digests
            and installed_entry.canceled_reservation_tombstones
            == tuple(
                sorted(
                    (
                        *prior_entry.canceled_reservation_tombstones,
                        *prior_entry.pending_reservation_digests,
                        *prior_entry.pre_release_commitment_digests,
                    )
                )
            )
            and fact.retained_outbox_item_digests
            == installed_entry.released_outbox_commitment_digests
            and fact.retained_active_drain_fact_digests
            == installed_entry.active_drain_fact_digests
            and receipt.canceled_reservation_digests
            == fact.canceled_reservation_digests
            and receipt.retained_outbox_item_digests
            == fact.retained_outbox_item_digests
            and receipt.retained_active_drain_fact_digests
            == fact.retained_active_drain_fact_digests
            and fact.deadline_intent_set_digest
            == (
                _intent_set_digest(context.deadline_intents)
                if context.deadline_intents
                else None
            )
            and receipt.deadline_conditions == context.deadline_conditions,
            "boundary terminal cancellation/retention/deadline DAG mismatch",
        )
        if fact.cause == "LOCAL_FIXED_DEADLINE_EXPIRED":
            _require(
                fact.server_terminal_receipt_digest is None
                and fact.renewal_fence_receipt_digest is None
                and len(context.deadline_intents) == 1
                and len(context.deadline_conditions) == 1
                and context.deadline_intents[0].purpose
                == EXPIRY_AT_OR_AFTER_EXCLUSIVE_DEADLINE
                and context.deadline_intents[0].deadline_kind
                == "BOUNDARY_GRANT_RELEASE_NOT_AFTER"
                and context.deadline_intents[0].exclusive_deadline
                == prior_entry.deadline.boundary_release_not_after
                and context.deadline_conditions[0].deadline_predicate_result
                and context.deadline_conditions[0].trusted_commit_time_sample
                >= prior_entry.deadline.boundary_release_not_after,
                "local terminal expiry lacks its one exact in-lock predicate",
            )
        elif fact.cause in {"SERVER_TERMINAL", "SERVER_RENEWAL_FENCE"}:
            _require(
                not context.deadline_intents and not context.deadline_conditions,
                "server-anchored boundary terminal carries an irrelevant local intent",
            )
            anchor_digest = (
                fact.server_terminal_receipt_digest
                if fact.cause == "SERVER_TERMINAL"
                else fact.renewal_fence_receipt_digest
            )
            _require(
                _is_hex64(anchor_digest)
                and (
                    fact.renewal_fence_receipt_digest is None
                    if fact.cause == "SERVER_TERMINAL"
                    else fact.server_terminal_receipt_digest is None
                ),
                "server terminal cause has missing or multiple authority anchors",
            )
            server_snapshots = tuple(
                value
                for value in staged_objects.values()
                if type(value) is ImmutableAuthoritySnapshot
                and value.store_id == "observer-authorization-server"
                and anchor_digest in _tuple_map(value.objects)
                and anchor_digest in _tuple_map(value.signed_bytes)
            )
            _require(
                len(server_snapshots) == 1,
                "server terminal cause lacks one exact authenticated snapshot",
            )
            server_snapshot = server_snapshots[0]
            _validate_atomic_snapshot(server_snapshot)
            server_objects = _tuple_map(server_snapshot.objects)
            server_signed = _tuple_map(server_snapshot.signed_bytes)
            anchor = server_objects.get(anchor_digest)
            if fact.cause == "SERVER_TERMINAL":
                _require(
                    type(anchor) is ObserverGrantTerminalTransitionReceipt,
                    "server terminal receipt anchor type is not exact",
                )
                terminal_fact = server_objects.get(anchor.transition_fact_digest)
                terminal_head = server_objects.get(anchor.installed_keyed_head_digest)
                matching_transitions = tuple(
                    transition
                    for transition in server_snapshot.transitions
                    if transition.transition_kind == "TERMINATE_GRANT"
                    and transition.installed_state_digest
                    == server_snapshot.state_digest
                    and anchor_digest in transition.specialized_receipt_digests
                )
                _require(
                    len(matching_transitions) == 1
                    and type(terminal_fact) is ObserverGrantTerminalTransitionFact
                    and type(terminal_head) is ObserverGrantLedgerHead
                    and terminal_fact.full_boundary_key == fact.full_boundary_key
                    and terminal_head.full_boundary_key == fact.full_boundary_key
                    and terminal_head.terminal_transition_fact_digest
                    == _digest(terminal_fact),
                    "server terminal receipt/fact/head are not one selected DAG",
                )
            else:
                _require(
                    type(anchor) is ObserverGrantRenewalPredecessorFenceReceipt,
                    "renewal fence anchor type is not exact",
                )
                matching_transitions = tuple(
                    transition
                    for transition in server_snapshot.transitions
                    if transition.transition_kind == "BEGIN_GRANT_RENEWAL"
                    and transition.installed_state_digest
                    == server_snapshot.state_digest
                    and anchor_digest in transition.specialized_receipt_digests
                )
                _require(
                    len(matching_transitions) == 1
                    and anchor.g0_full_boundary_key == fact.full_boundary_key,
                    "renewal fence is not the selected G0-consuming transition",
                )
            anchor_transition = matching_transitions[0]
            _verify_signed_bytes(
                anchor,
                server_signed[anchor_digest],
                expected_principal=server_snapshot.authority_principal,
                expected_key_id=anchor_transition.signing_key_id,
                expected_security_state=anchor_transition.security_state_digest,
            )
        else:
            raise ProbeError(
                "boundary terminal cause is outside the closed evidence union"
            )
    else:
        raise ProbeError("boundary transition lacks closed semantic dispatch")


_CANONICAL_ARTIFACT_TYPE_REGISTRY: tuple[tuple[type[Any], str], ...] = (
    (SignedArtifact, "ncp.b01.artifact.SignedArtifact@1"),
    (
        ParentSelectorAllocationReceipt,
        "ncp.b01.artifact.ParentSelectorAllocationReceipt@1",
    ),
    (
        CommitTimeDeadlineCondition,
        "ncp.b01.artifact.CommitTimeDeadlineCondition@1",
    ),
    (AuthenticatedClockMapping, "ncp.b01.artifact.AuthenticatedClockMapping@1"),
    (BoundaryMember, "ncp.b01.artifact.BoundaryMember@1"),
    (BoundaryDeadline, "ncp.b01.artifact.BoundaryDeadline@1"),
    (ObserverGrantRegistryKey, "ncp.b01.artifact.ObserverGrantRegistryKey@1"),
    (
        TrustedDeliveryBoundaryGrantKey,
        "ncp.b01.artifact.TrustedDeliveryBoundaryGrantKey@1",
    ),
    (
        ObserverGrantBoundaryInstallationPlan,
        "ncp.b01.artifact.ObserverGrantBoundaryInstallationPlan@1",
    ),
    (ObserverGrant, "ncp.b01.artifact.ObserverGrant@1"),
    (AtomicTransitionRecord, "ncp.b01.artifact.AtomicTransitionRecord@1"),
    (
        ImmutableAuthoritySnapshot,
        "ncp.b01.artifact.ImmutableAuthoritySnapshot@1",
    ),
    (AtomicReceiptContext, "ncp.b01.artifact.AtomicReceiptContext@1"),
    (AtomicReceiptBundle, "ncp.b01.artifact.AtomicReceiptBundle@1"),
    (AtomicCandidate, "ncp.b01.artifact.AtomicCandidate@1"),
    (
        AuthorityTransitionOperationCommitment,
        "ncp.b01.artifact.AuthorityTransitionOperationCommitment@1",
    ),
    (
        AuthorizationDeadlineConditionIntent,
        "ncp.b01.artifact.AuthorizationDeadlineConditionIntent@1",
    ),
    (
        AuthorizationDeadlineConditionIntentSet,
        "ncp.b01.artifact.AuthorizationDeadlineConditionIntentSet@1",
    ),
    (
        CanonicalObserverReadScope,
        "ncp.b01.bridge.CanonicalObserverReadScope@1",
    ),
    (
        ObserverBoundaryReadScopeMembership,
        "ncp.b01.bridge.ObserverBoundaryReadScopeMembership@1",
    ),
    (
        SyntheticVerifiedAuthorizationIngressContext,
        "ncp.b01.bridge.SyntheticVerifiedAuthorizationIngressContext@1",
    ),
    (
        SyntheticVerifiedReleaseRecipientContext,
        "ncp.b01.bridge.SyntheticVerifiedReleaseRecipientContext@1",
    ),
    (
        ExpectedQualifiedDeadlineMappingStateCut,
        "ncp.b01.bridge.ExpectedQualifiedDeadlineMappingStateCut@1",
    ),
    (
        QualifiedDecisionDeadlineMapping,
        "ncp.b01.bridge.QualifiedDecisionDeadlineMapping@1",
    ),
    (
        ExpectedGrantCurrentnessStateCut,
        "ncp.b01.bridge.ExpectedGrantCurrentnessStateCut@1",
    ),
    (
        SyntheticAuthenticatedGrantCurrentnessEvidence,
        "ncp.b01.bridge.SyntheticAuthenticatedGrantCurrentnessEvidence@1",
    ),
    (
        ObserverReadReleaseCAS,
        "ncp.b01.bridge.ObserverReadReleaseCAS@1",
    ),
    (
        SyntheticValidatedObserverReadReleaseCASReceipt,
        "ncp.b01.bridge.SyntheticValidatedObserverReadReleaseCASReceipt@1",
    ),
    (
        SyntheticCommittedObserverReadOutboxArtifact,
        "ncp.b01.bridge.SyntheticCommittedObserverReadOutboxArtifact@1",
    ),
    (
        SyntheticObserverReadOutboxCommitReceipt,
        "ncp.b01.bridge.SyntheticObserverReadOutboxCommitReceipt@1",
    ),
    (
        ExpectedCommittedObserverReadOutboxStateCut,
        "ncp.b01.bridge.ExpectedCommittedObserverReadOutboxStateCut@1",
    ),
    (
        ExpectedDispatchDestinationCut,
        "ncp.b01.bridge.ExpectedDispatchDestinationCut@1",
    ),
    (
        SyntheticAuthenticatedDispatchContext,
        "ncp.b01.bridge.SyntheticAuthenticatedDispatchContext@1",
    ),
    (
        ExpectedObserverReadAuthorizationCut,
        "ncp.b01.bridge.ExpectedObserverReadAuthorizationCut@1",
    ),
    (
        SealedObserverReadAuthorizationDecision,
        "ncp.b01.bridge.SealedObserverReadAuthorizationDecision@1",
    ),
    (
        ObserverDefaultDenyManifestEntry,
        "ncp.b01.artifact.ObserverDefaultDenyManifestEntry@1",
    ),
    (
        ObserverDefaultDenyManifest,
        "ncp.b01.artifact.ObserverDefaultDenyManifest@1",
    ),
    (
        VerifiedObserverTransportPrincipal,
        "ncp.b01.artifact.VerifiedObserverTransportPrincipal@1",
    ),
    (ObserverDescriptor, "ncp.b01.artifact.ObserverDescriptor@1"),
    (ObserverReadCapability, "ncp.b01.artifact.ObserverReadCapability@1"),
    (
        ObserverReadCapabilitySeal,
        "ncp.b01.artifact.ObserverReadCapabilitySeal@1",
    ),
    (
        ObserverReadCapabilityIssuerSnapshot,
        "ncp.b01.artifact.ObserverReadCapabilityIssuerSnapshot@1",
    ),
    (
        ObserverReadCapabilityEvidence,
        "ncp.b01.artifact.ObserverReadCapabilityEvidence@1",
    ),
    (ObserverAttached, "ncp.b01.artifact.ObserverAttached@1"),
    (ObserverGrantLedgerHead, "ncp.b01.artifact.ObserverGrantLedgerHead@1"),
    (
        ObserverGrantRegistryHead,
        "ncp.b01.artifact.ObserverGrantRegistryHead@1",
    ),
    (
        ObserverAuthorizationStateHead,
        "ncp.b01.artifact.ObserverAuthorizationStateHead@1",
    ),
    (
        InstalledObserverAuthorizationStateSelector,
        "ncp.b01.artifact.InstalledObserverAuthorizationStateSelector@1",
    ),
    (
        ObserverAuthorizationStateCommitReceipt,
        "ncp.b01.artifact.ObserverAuthorizationStateCommitReceipt@1",
    ),
    (
        ObserverGrantRegistryCommitReceipt,
        "ncp.b01.artifact.ObserverGrantRegistryCommitReceipt@1",
    ),
    (
        ObserverGrantBoundaryInstallationCommitment,
        "ncp.b01.artifact.ObserverGrantBoundaryInstallationCommitment@1",
    ),
    (
        ObserverGrantBoundaryInstallationSetReceipt,
        "ncp.b01.artifact.ObserverGrantBoundaryInstallationSetReceipt@1",
    ),
    (
        ObserverGrantRegistryActivationEntryProof,
        "ncp.b01.artifact.ObserverGrantRegistryActivationEntryProof@1",
    ),
    (
        ObserverGrantRenewalPredecessorFenceReceipt,
        "ncp.b01.artifact.ObserverGrantRenewalPredecessorFenceReceipt@1",
    ),
    (
        ObserverGrantRenewalTransitionFact,
        "ncp.b01.artifact.ObserverGrantRenewalTransitionFact@1",
    ),
    (
        ObserverGrantBoundaryInstallationFailureMemberEvidence,
        "ncp.b01.artifact.ObserverGrantBoundaryInstallationFailureMemberEvidence@1",
    ),
    (
        ObserverGrantTerminalTransitionFact,
        "ncp.b01.artifact.ObserverGrantTerminalTransitionFact@1",
    ),
    (
        ObserverGrantTerminalTransitionReceipt,
        "ncp.b01.artifact.ObserverGrantTerminalTransitionReceipt@1",
    ),
    (
        ObserverGrantReattachmentPolicyResult,
        "ncp.b01.artifact.ObserverGrantReattachmentPolicyResult@1",
    ),
    (
        ObserverAuthorizationClockRestartTransitionFact,
        "ncp.b01.artifact.ObserverAuthorizationClockRestartTransitionFact@1",
    ),
    (
        ObserverAuthorizationClockRestartCommitReceipt,
        "ncp.b01.artifact.ObserverAuthorizationClockRestartCommitReceipt@1",
    ),
    (ServerActivationResult, "ncp.b01.artifact.ServerActivationResult@1"),
    (ServerRenewalResult, "ncp.b01.artifact.ServerRenewalResult@1"),
    (ServerTerminalResult, "ncp.b01.artifact.ServerTerminalResult@1"),
    (
        TrustedDeliveryBoundaryGrantPreparationFact,
        "ncp.b01.artifact.TrustedDeliveryBoundaryGrantPreparationFact@1",
    ),
    (
        TrustedDeliveryBoundaryGrantStateHead,
        "ncp.b01.artifact.TrustedDeliveryBoundaryGrantStateHead@1",
    ),
    (
        TrustedDeliveryBoundaryGrantMapHead,
        "ncp.b01.artifact.TrustedDeliveryBoundaryGrantMapHead@1",
    ),
    (
        TrustedDeliveryReleaseStateHead,
        "ncp.b01.artifact.TrustedDeliveryReleaseStateHead@1",
    ),
    (
        InstalledTrustedDeliveryReleaseSelector,
        "ncp.b01.artifact.InstalledTrustedDeliveryReleaseSelector@1",
    ),
    (
        TrustedDeliveryReleaseStateCommitReceipt,
        "ncp.b01.artifact.TrustedDeliveryReleaseStateCommitReceipt@1",
    ),
    (
        TrustedDeliveryBoundaryGrantMapCommitReceipt,
        "ncp.b01.artifact.TrustedDeliveryBoundaryGrantMapCommitReceipt@1",
    ),
    (
        TrustedDeliveryBoundaryGrantEnforcementReceipt,
        "ncp.b01.artifact.TrustedDeliveryBoundaryGrantEnforcementReceipt@1",
    ),
    (
        TrustedDeliveryBoundaryGrantActivationFact,
        "ncp.b01.artifact.TrustedDeliveryBoundaryGrantActivationFact@1",
    ),
    (
        TrustedDeliveryBoundaryGrantActivationReceipt,
        "ncp.b01.artifact.TrustedDeliveryBoundaryGrantActivationReceipt@1",
    ),
    (
        TrustedDeliveryReleaseReservation,
        "ncp.b01.artifact.TrustedDeliveryReleaseReservation@1",
    ),
    (
        TrustedDeliveryReleaseOutboxCommitment,
        "ncp.b01.artifact.TrustedDeliveryReleaseOutboxCommitment@1",
    ),
    (
        TrustedDeliveryReleaseReceipt,
        "ncp.b01.artifact.TrustedDeliveryReleaseReceipt@1",
    ),
    (
        TrustedDeliveryReleaseOutbox,
        "ncp.b01.artifact.TrustedDeliveryReleaseOutbox@1",
    ),
    (
        TrustedDeliveryExternalTransportDrainFact,
        "ncp.b01.artifact.TrustedDeliveryExternalTransportDrainFact@1",
    ),
    (
        TrustedDeliveryExternalTransportDisposition,
        "ncp.b01.artifact.TrustedDeliveryExternalTransportDisposition@1",
    ),
    (
        SyntheticAuthenticatedTransportDispositionEvidence,
        "ncp.b01.artifact.SyntheticAuthenticatedTransportDispositionEvidence@1",
    ),
    (
        SyntheticReceiverDeduplicationRetryProof,
        "ncp.b01.artifact.SyntheticReceiverDeduplicationRetryProof@1",
    ),
    (
        TrustedDeliveryBoundaryTerminalTransitionFact,
        "ncp.b01.artifact.TrustedDeliveryBoundaryTerminalTransitionFact@1",
    ),
    (
        TrustedDeliveryBoundaryBulkTerminalTransitionFact,
        "ncp.b01.artifact.TrustedDeliveryBoundaryBulkTerminalTransitionFact@1",
    ),
    (
        TrustedDeliveryBoundaryTerminalInstallationReceipt,
        "ncp.b01.artifact.TrustedDeliveryBoundaryTerminalInstallationReceipt@1",
    ),
    (
        TrustedDeliveryBoundaryTransportQuiescenceFact,
        "ncp.b01.artifact.TrustedDeliveryBoundaryTransportQuiescenceFact@1",
    ),
    (
        TrustedDeliveryBoundaryTransportQuiescenceReceipt,
        "ncp.b01.artifact.TrustedDeliveryBoundaryTransportQuiescenceReceipt@1",
    ),
    (
        TrustedDeliveryBoundaryClockRestartBridge,
        "ncp.b01.artifact.TrustedDeliveryBoundaryClockRestartBridge@1",
    ),
    (
        TrustedDeliveryBoundaryClockRestartCommitReceipt,
        "ncp.b01.artifact.TrustedDeliveryBoundaryClockRestartCommitReceipt@1",
    ),
    (BoundaryPreparationResult, "ncp.b01.artifact.BoundaryPreparationResult@1"),
    (BoundaryActivationResult, "ncp.b01.artifact.BoundaryActivationResult@1"),
    (BoundaryReleaseResult, "ncp.b01.artifact.BoundaryReleaseResult@1"),
    (BoundaryTerminalResult, "ncp.b01.artifact.BoundaryTerminalResult@1"),
)

for _canonical_type, _canonical_type_id in _CANONICAL_ARTIFACT_TYPE_REGISTRY:
    _register_artifact_type(_canonical_type, _canonical_type_id)


@dataclass(frozen=True)
class ObserverAuthorizationCompositeEvidence:
    server_snapshot: ImmutableAuthoritySnapshot
    boundary_snapshots: tuple[ImmutableAuthoritySnapshot, ...]
    default_deny_manifest: ObserverDefaultDenyManifest
    capability_evidence: ObserverReadCapabilityEvidence
    plan: ObserverGrantBoundaryInstallationPlan
    grant: ObserverGrant
    server_activation: ServerActivationResult
    read_authorization_decision: SealedObserverReadAuthorizationDecision
    retained_read_authorization_cut: ExpectedObserverReadAuthorizationCut
    read_authorization_exact_retry: SealedObserverReadAuthorizationDecision
    boundary_preparations: tuple[BoundaryPreparationResult, ...]
    boundary_activations: tuple[BoundaryActivationResult, ...]
    release: BoundaryReleaseResult
    drain_fact: TrustedDeliveryExternalTransportDrainFact
    drain_disposition: TrustedDeliveryExternalTransportDisposition


_register_artifact_type(
    ObserverAuthorizationCompositeEvidence,
    "ncp.b01.artifact.ObserverAuthorizationCompositeEvidence@1",
)
_CANONICAL_ARTIFACT_TYPE_IDS = FrozenTypeRegistry(
    tuple(_CANONICAL_ARTIFACT_TYPE_IDS.items())
)


def _retain_read_authorization_cut(
    decision: SealedObserverReadAuthorizationDecision,
) -> ExpectedObserverReadAuthorizationCut:
    """Retain the verifier's exact authorization cut, not candidate fields later."""

    return ExpectedObserverReadAuthorizationCut(
        authorization_ingress_artifact_digest=(
            authorization_ingress_artifact_digest(
                decision.authorization_ingress_context
            )
        ),
        authorization_endpoint_profile=(
            decision.authorization_ingress_context.endpoint_profile
        ),
        authorization_connection_instance=(
            decision.authorization_ingress_context.connection_instance
        ),
        authorization_replay_domain=(
            decision.authorization_ingress_context.replay_domain
        ),
        capability_digest=decision.capability_digest,
        capability_seal_digest=decision.capability_seal_digest,
        capability_issuer_snapshot_digest=(decision.capability_issuer_snapshot_digest),
        manifest_digest=decision.manifest_digest,
        manifest_entry_digest=decision.manifest_entry_digest,
        stable_grant_key_digest=decision.stable_grant_key_digest,
        full_boundary_key_digest=decision.full_boundary_key_digest,
        grant_digest=decision.grant_digest,
        server_entry_head_digest=decision.server_entry_head_digest,
        server_selector_digest=decision.server_selector_digest,
        authority_realm_key=decision.authority_realm_key,
        source_session_kind=decision.source_session_kind,
        logical_session_id=decision.logical_session_id,
        source_generation=decision.source_generation,
        security_state_digest=decision.security_state_digest,
        security_epoch=decision.security_epoch,
        revocation_epoch=decision.revocation_epoch,
        coordinator_clock_incarnation=decision.coordinator_clock_incarnation,
        exclusive_not_after=decision.exclusive_not_after,
        maximum_release_count=decision.maximum_release_count,
    )


def _fixture_read_scope(
    *,
    boundary_principal: str,
    route_class: str = "OBSERVATION_FRAME",
) -> ObserverManifestReadScope:
    operation = (
        "subscribe" if boundary_principal == "delivery-gateway-a" else "history_query"
    )
    plane, message_class = READ_ROUTE_CLASS_SHAPES[route_class]
    channel = (
        "pose_position"
        if route_class
        in {
            "ACTION_COMMAND_PROPOSAL",
            "PERCEPTION_PROJECTED_OBSERVATION",
            "PERCEPTION_SENSOR_FRAME",
        }
        else ""
    )
    scope = ObserverManifestReadScope(
        authority_realm_key=AUTHORITY_REALM_KEY,
        source_session_kind="NCP_SESSION",
        logical_session_id=SESSION_ID,
        source_generation=SESSION_GENERATION,
        operation=operation,
        route_class=route_class,
        plane=plane,
        literal_route=canonical_read_route(
            realm=AUTHORITY_REALM_KEY[1],
            logical_session_id=SESSION_ID,
            route_class=route_class,
            channel=channel,
        ),
        message_class=message_class,
        channel=channel,
        extension="none",
        declared_stream_digest=hashlib.sha256(
            f"declared-stream:{route_class}".encode()
        ).hexdigest(),
        schema_digest=hashlib.sha256(f"schema:{message_class}".encode()).hexdigest(),
        provider_contract_digest=hashlib.sha256(
            f"provider-contract:{boundary_principal}".encode()
        ).hexdigest(),
        privacy_projection_digest=hashlib.sha256(
            b"privacy-projection:observer-a"
        ).hexdigest(),
        authorization_audience=SERVER_PRINCIPAL,
        history_clock_domain=(
            "provider-sequence" if operation == "history_query" else None
        ),
        history_clock_incarnation=(
            SESSION_GENERATION if operation == "history_query" else None
        ),
        history_window_start=(10 if operation == "history_query" else None),
        history_window_end=(20 if operation == "history_query" else None),
        scope_digest="",
    )
    return seal_scope(scope)


def _fixture_members() -> tuple[BoundaryMember, ...]:
    definitions = (
        (
            "delivery-gateway-a",
            "gateway-instance-a",
            "00000000-0000-4000-8000-000000000301",
            "delivery-gateway-a:key:4",
            1_000,
            1_002,
            1,
            1,
            11,
            10,
        ),
        (
            "history-provider-b",
            "history-instance-b",
            "00000000-0000-4000-8000-000000000302",
            "history-provider-b:key:9",
            2_000,
            2_003,
            9,
            10,
            6,
            5,
        ),
    )
    members: list[BoundaryMember] = []
    for (
        principal,
        instance,
        clock,
        key_id,
        reference_lower,
        reference_upper,
        minimum_rate_numerator,
        minimum_rate_denominator,
        maximum_rate_numerator,
        maximum_rate_denominator,
    ) in definitions:
        mapping = AuthenticatedClockMapping(
            coordinator_clock_incarnation=SERVER_CLOCK_1,
            boundary_clock_incarnation=clock,
            coordinator_reference=100,
            boundary_reference_lower=reference_lower,
            boundary_reference_upper=reference_upper,
            source_applicability_start=90,
            source_applicability_end=250,
            target_applicability_start=900,
            target_applicability_end=2_300,
            minimum_rate_numerator=minimum_rate_numerator,
            minimum_rate_denominator=minimum_rate_denominator,
            maximum_rate_numerator=maximum_rate_numerator,
            maximum_rate_denominator=maximum_rate_denominator,
            rounding_rule="LOWER_FLOOR_UPPER_CEIL",
            correlation_authority="qualified-clock-authority",
            qualification_digest=hashlib.sha256(
                f"qualification:{instance}".encode()
            ).hexdigest(),
            source_receipt_digest=hashlib.sha256(
                f"source-receipt:{instance}".encode()
            ).hexdigest(),
            source_receipt_authority="qualified-clock-authority",
            source_receipt_current=True,
        )
        read_scope = _fixture_read_scope(
            boundary_principal=principal,
        )
        delivery_domain = (
            read_scope.literal_route
            if read_scope.operation == "subscribe"
            else canonical_history_delivery_domain(read_scope)
        )
        membership = seal_boundary_membership(
            ObserverBoundaryReadScopeMembership(
                canonical_scope_digest=read_scope.scope_digest,
                boundary_principal=principal,
                boundary_instance=instance,
                delivery_domain_kind=(
                    LIVE_ROUTE_DOMAIN
                    if read_scope.operation == "subscribe"
                    else HISTORY_CONTENT_DOMAIN
                ),
                delivery_domain=delivery_domain,
                deadline_policy_id=f"{instance}:deadline-policy:v1",
                membership_digest="",
            )
        )
        members.append(
            BoundaryMember(
                boundary_principal=principal,
                boundary_instance=instance,
                delivery_domain=delivery_domain,
                deadline_policy_id=f"{instance}:deadline-policy:v1",
                read_scope=read_scope,
                scope_membership=membership,
                security_state_digest=hashlib.sha256(
                    f"security:{instance}".encode()
                ).hexdigest(),
                security_key_id=key_id,
                clock_mapping=mapping,
            )
        )
    return tuple(sorted(members, key=lambda item: _canonical_bytes(item.identity)))


def _fixture_default_deny_manifest(
    members: tuple[BoundaryMember, ...],
) -> ObserverDefaultDenyManifest:
    manifest = ObserverDefaultDenyManifest(
        manifest_id="observer-default-deny-manifest-v1",
        manifest_version=1,
        issuer_principal=SERVER_PRINCIPAL,
        issuer_key_id=SERVER_KEY_ID,
        capability_issuer_principal=CAPABILITY_ISSUER_PRINCIPAL,
        capability_issuer_key_id=CAPABILITY_ISSUER_KEY_ID,
        capability_issuer_incarnation=CAPABILITY_ISSUER_INCARNATION,
        authority_realm_key=AUTHORITY_REALM_KEY,
        default_decision="DENY",
        wildcard_entries_allowed=False,
        entries=(
            ObserverDefaultDenyManifestEntry(
                authority_realm_key=AUTHORITY_REALM_KEY,
                authenticated_principal="observer-a",
                endpoint_profile="production-secure",
                audience=SERVER_PRINCIPAL,
                logical_session=SESSION_ID,
                session_generation=SESSION_GENERATION,
                operations=OBSERVER_READ_OPERATIONS,
                read_scopes=tuple(
                    sorted(
                        (member.read_scope for member in members),
                        key=lambda scope: scope.scope_digest,
                    )
                ),
                security_state_digest=SECURITY_STATE_DIGEST,
                security_epoch=7,
                revocation_epoch=11,
            ),
        ),
    )
    _validate_default_deny_manifest(manifest)
    return manifest


def _fixture_capability_evidence(
    manifest: ObserverDefaultDenyManifest,
) -> ObserverReadCapabilityEvidence:
    context = VerifiedObserverTransportPrincipal(
        authority_realm_key=AUTHORITY_REALM_KEY,
        authenticated_principal="observer-a",
        connection_instance="tls-connection-observer-a-1",
        replay_domain="observer-ingress-replay-domain-a",
        endpoint_profile="production-secure",
        audience=SERVER_PRINCIPAL,
        logical_session=SESSION_ID,
        session_generation=SESSION_GENERATION,
        default_deny_manifest_digest=_digest(manifest),
        security_state_digest=SECURITY_STATE_DIGEST,
        security_epoch=7,
        revocation_epoch=11,
        coordinator_clock_incarnation=SERVER_CLOCK_1,
        verified_at=100,
        not_after=200,
        transport_verification_evidence_digest=hashlib.sha256(
            b"synthetic-verified-tls-principal-observer-a"
        ).hexdigest(),
    )
    return ObserverReadCapabilityIssuer().issue(
        manifest=manifest,
        context=context,
        trusted_time=100,
    )


def _build_smoke_evidence() -> ObserverAuthorizationCompositeEvidence:
    members = _fixture_members()
    manifest = _fixture_default_deny_manifest(members)
    capability_evidence = _fixture_capability_evidence(manifest)
    descriptor = ObserverDescriptor(
        responder_principal=SERVER_PRINCIPAL,
        authority_realm_key=AUTHORITY_REALM_KEY,
        descriptor_revision=1,
        logical_session=SESSION_ID,
        session_generation=SESSION_GENERATION,
        security_state_digest=SECURITY_STATE_DIGEST,
        security_epoch=7,
        revocation_epoch=11,
        privacy_policy_digest=hashlib.sha256(b"privacy-v1").hexdigest(),
        declared_stream_digest=hashlib.sha256(b"declared-stream-v1").hexdigest(),
        allowed_boundary_member_identities=tuple(member.identity for member in members),
    )
    server = ObserverAuthorizationServer()
    server.genesis(descriptor, manifest=manifest, commit_time=90)
    boundaries = tuple(TrustedDeliveryBoundary(member) for member in members)
    for boundary, local_time in zip(
        boundaries,
        (990, 1_990),
        strict=True,
    ):
        boundary.genesis(commit_time=local_time)
    registry_key = ObserverGrantRegistryKey(
        requester_principal="observer-a",
        grant_lineage_incarnation=_uuid_for(("observer-a", "lineage")),
    )
    plan = _build_plan(
        key=registry_key,
        issuance_sequence=1,
        issuance_context_digest=hashlib.sha256(b"issuance:g0").hexdigest(),
        operation="ATTACH_NEW_GRANT_LINEAGE",
        challenge=_uuid_for(("observer-a", "attach-challenge")),
        context_digest=hashlib.sha256(b"attach-context").hexdigest(),
        descriptor_revision=descriptor.descriptor_revision,
        descriptor_digest=_digest(descriptor),
        privacy_policy_digest=descriptor.privacy_policy_digest,
        members=members,
        scope_digests=tuple(sorted(member.exact_scope_digest for member in members)),
        server_clock=SERVER_CLOCK_1,
        request_time=100,
        installation_close=120,
        grant_not_after=200,
        minimum_budget=10,
        maximum_lag=60,
    )
    grant = _seal_grant(plan, sequence_label="observer-a:g0")
    server.install_pending(
        plan,
        grant,
        transition_kind="ATTACH_NEW_GRANT_LINEAGE",
        predecessor_closure_receipt_digest=None,
        commit_time=105,
    )
    preparations = tuple(
        boundary.prepare(
            server=server,
            plan=plan,
            grant=grant,
            predecessor_closure_receipt_digest=None,
            predecessor_key=None,
            commit_time=deadline.boundary_prepare_close - 1,
        )
        for boundary, deadline in zip(
            boundaries,
            plan.boundary_deadlines,
            strict=True,
        )
    )
    server_activation = server.activate(
        registry_key,
        prepared_boundaries=tuple(
            (boundary.store, preparation)
            for boundary, preparation in zip(
                boundaries,
                preparations,
                strict=True,
            )
        ),
        predecessor_closure_receipt_digest=None,
        capability_evidence=capability_evidence,
        commit_time=110,
    )
    subscribe_member = next(
        member for member in members if member.read_scope.operation == "subscribe"
    )
    read_authorization_decision = server.authorize_read(
        capability_evidence,
        live_transport_context=capability_evidence.verified_transport_context,
        read_scope=subscribe_member.read_scope,
        boundary_membership=subscribe_member.scope_membership,
        expected_boundary_identity=(
            subscribe_member.boundary_principal,
            subscribe_member.boundary_instance,
            subscribe_member.deadline_policy_id,
        ),
        observer_instance=OBSERVER_INSTANCE,
        caller_operation_id=_uuid_for(("observer-read", "subscribe", 1)),
        trusted_time=111,
    )
    read_authorization_exact_retry = server.authorize_read(
        capability_evidence,
        live_transport_context=capability_evidence.verified_transport_context,
        read_scope=subscribe_member.read_scope,
        boundary_membership=subscribe_member.scope_membership,
        expected_boundary_identity=(
            subscribe_member.boundary_principal,
            subscribe_member.boundary_instance,
            subscribe_member.deadline_policy_id,
        ),
        observer_instance=OBSERVER_INSTANCE,
        caller_operation_id=_uuid_for(("observer-read", "subscribe", 1)),
        trusted_time=111,
    )
    _require(
        read_authorization_exact_retry == read_authorization_decision,
        "exact same-context read admission retry changed its decision identity",
    )
    activations = tuple(
        boundary.activate(
            preparation=preparation,
            server=server,
            server_activation=server_activation,
            commit_time=deadline.boundary_latest_server_activation_at + 1,
        )
        for boundary, preparation, deadline in zip(
            boundaries,
            preparations,
            plan.boundary_deadlines,
            strict=True,
        )
    )
    payload = b"synthetic bounded observation"
    reservation_commit_time = (
        plan.boundary_deadlines[0].boundary_latest_server_activation_at + 2
    )
    release_recipient_context = seal_release_recipient_context(
        SyntheticVerifiedReleaseRecipientContext(
            provenance_kind=("SYNTHETIC_VERIFIED_BOUNDARY_LOCAL_RELEASE_RECIPIENT"),
            boundary_principal=subscribe_member.boundary_principal,
            boundary_instance=subscribe_member.boundary_instance,
            recipient_principal=OBSERVER_PRINCIPAL,
            recipient_instance=OBSERVER_INSTANCE,
            connection_instance="observer-release-connection-a-2",
            replay_domain="observer-release-replay-domain-a-2",
            endpoint_profile="production-secure",
            boundary_scope_membership_digest=(
                subscribe_member.scope_membership.membership_digest
            ),
            local_security_state_digest=subscribe_member.security_state_digest,
            local_security_epoch=plan.security_epoch,
            local_revocation_epoch=plan.revocation_epoch,
            boundary_clock_incarnation=(
                subscribe_member.clock_mapping.boundary_clock_incarnation
            ),
            verified_at=reservation_commit_time - 1,
            exclusive_not_after=(
                _map_lower(
                    subscribe_member.clock_mapping,
                    read_authorization_decision.exclusive_not_after,
                )
                - 1
            ),
            semantic_context_digest="",
            fixture_authentication_tag="",
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    reservation = boundaries[0].create_reservation(
        activation=activations[0],
        payload=payload,
        read_scope=subscribe_member.read_scope,
        boundary_membership=subscribe_member.scope_membership,
        read_authorization_decision=read_authorization_decision,
        retained_authorization_cut=_retain_read_authorization_cut(
            read_authorization_decision
        ),
        release_recipient_context=release_recipient_context,
        expected_release_transport_context=(
            "production-secure",
            "observer-release-connection-a-2",
            "observer-release-replay-domain-a-2",
        ),
        expected_release_context_artifact_digest=(
            release_recipient_artifact_digest(release_recipient_context)
        ),
        release_idempotency_key=_uuid_for(("release-request", "a", 1)),
        commit_time=reservation_commit_time,
    )
    release = boundaries[0].release_to_outbox(
        reservation=reservation,
        preparation=preparations[0],
        activation=activations[0],
        payload=payload,
        commit_time=plan.boundary_deadlines[0].boundary_latest_server_activation_at + 3,
    )
    dispatch_commit_time = (
        plan.boundary_deadlines[0].boundary_latest_server_activation_at + 4
    )
    dispatch_attempt_id = _uuid_for(
        (
            release.outbox_item.attempt_namespace,
            1,
            boundaries[0].head.next_attempt_sequence,
        )
    )
    expected_dispatch_transport_context = (
        "production-secure",
        "observer-dispatch-connection-a-3",
        "observer-dispatch-replay-domain-a-3",
    )
    transport_gate_epoch = boundaries[0].store.snapshot.snapshot_version
    expected_dispatch_destination_cut = ExpectedDispatchDestinationCut(
        boundary_principal=subscribe_member.boundary_principal,
        boundary_instance=subscribe_member.boundary_instance,
        recipient_principal=OBSERVER_PRINCIPAL,
        recipient_instance=OBSERVER_INSTANCE,
        canonical_scope_digest=subscribe_member.read_scope.scope_digest,
        boundary_scope_membership_digest=(
            subscribe_member.scope_membership.membership_digest
        ),
        stable_outbox_item_id=release.outbox_item.stable_item_id,
        endpoint_profile=expected_dispatch_transport_context[0],
        connection_instance=expected_dispatch_transport_context[1],
        replay_domain=expected_dispatch_transport_context[2],
        boundary_clock_incarnation=(
            subscribe_member.clock_mapping.boundary_clock_incarnation
        ),
        local_security_state_digest=subscribe_member.security_state_digest,
        local_security_epoch=plan.security_epoch,
        local_revocation_epoch=plan.revocation_epoch,
        transport_gate_state_digest="0" * 64,
        transport_gate_epoch=transport_gate_epoch,
        exclusive_not_after=(
            release.reservation.release_cas.effective_release_not_after
        ),
    )
    expected_dispatch_destination_cut = replace(
        expected_dispatch_destination_cut,
        transport_gate_state_digest=dispatch_transport_gate_state_digest(
            expected_dispatch_destination_cut
        ),
    )
    transport_gate_state_digest = (
        expected_dispatch_destination_cut.transport_gate_state_digest
    )
    dispatch_context = seal_dispatch_context(
        SyntheticAuthenticatedDispatchContext(
            provenance_kind="SYNTHETIC_FRESH_AUTHENTICATED_OUTBOX_DISPATCH",
            dispatch_verification_event_id=_uuid_for(
                ("dispatch-verification", release.outbox_item.stable_item_id, 1)
            ),
            dispatch_attempt_id=dispatch_attempt_id,
            boundary_principal=subscribe_member.boundary_principal,
            boundary_instance=subscribe_member.boundary_instance,
            recipient_principal=OBSERVER_PRINCIPAL,
            recipient_instance=OBSERVER_INSTANCE,
            canonical_scope_digest=subscribe_member.read_scope.scope_digest,
            boundary_scope_membership_digest=(
                subscribe_member.scope_membership.membership_digest
            ),
            stable_outbox_item_id=release.outbox_item.stable_item_id,
            stable_payload_digest=release.outbox_item.payload_digest,
            payload_octet_length=release.outbox_item.payload_length,
            committed_outbox_artifact_digest=(
                committed_outbox_artifact_digest(
                    release.outbox_item.committed_bridge_outbox_artifact
                )
            ),
            validated_release_cas_receipt_artifact_digest=(
                validated_release_cas_receipt_artifact_digest(
                    release.reservation.validated_release_cas_receipt
                )
            ),
            outbox_commit_receipt_artifact_digest=(
                outbox_commit_receipt_artifact_digest(
                    release.outbox_item.bridge_commit_receipt
                )
            ),
            installed_outbox_storage_state_head_digest=(
                release.outbox_item.bridge_commit_receipt.installed_storage_state_head_digest
            ),
            outbox_transaction_id=(
                release.outbox_item.bridge_commit_receipt.transaction_id
            ),
            outbox_identity_digest=(
                release.outbox_item.committed_bridge_outbox_artifact.outbox_identity_digest
            ),
            release_cas_artifact_digest=(release.reservation.release_cas.cas_digest),
            release_recipient_context_artifact_digest=(
                release_recipient_artifact_digest(release_recipient_context)
            ),
            release_ordinal=release.reservation.release_cas.release_ordinal,
            installed_release_counter_state_digest=(
                release.reservation.release_cas.next_release_counter_state_digest
            ),
            transport_idempotency_key=release.outbox_item.idempotency_key,
            endpoint_profile=expected_dispatch_transport_context[0],
            connection_instance=expected_dispatch_transport_context[1],
            replay_domain=expected_dispatch_transport_context[2],
            destination_cut_digest=dispatch_destination_cut_digest(
                expected_dispatch_destination_cut
            ),
            transport_gate_state_digest=transport_gate_state_digest,
            transport_gate_epoch=transport_gate_epoch,
            boundary_clock_incarnation=(
                subscribe_member.clock_mapping.boundary_clock_incarnation
            ),
            local_security_state_digest=subscribe_member.security_state_digest,
            local_security_epoch=plan.security_epoch,
            local_revocation_epoch=plan.revocation_epoch,
            verified_at=dispatch_commit_time,
            exclusive_not_after=release.reservation.release_cas.effective_release_not_after,
            semantic_context_digest="",
            fixture_authentication_tag="",
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    drain_fact = boundaries[0].start_external_drain(
        release=release,
        actual_dispatch_payload=release.outbox_item.complete_payload,
        dispatch_context=dispatch_context,
        expected_dispatch_destination_cut=expected_dispatch_destination_cut,
        expected_dispatch_context_artifact_digest=(
            dispatch_artifact_digest(dispatch_context)
        ),
        receiver_dedup_retry_proof=None,
        commit_time=dispatch_commit_time,
    )
    boundaries[0].enqueue_external_transport_for_test(
        fact=drain_fact,
        exact_payload=release.outbox_item.complete_payload,
        enqueue_time=dispatch_commit_time,
    )
    transport_result_time = (
        plan.boundary_deadlines[0].boundary_latest_server_activation_at + 5
    )
    disposition = boundaries[0].resolve_external_drain(
        fact=drain_fact,
        outcome="DELIVERED",
        transport_evidence=_fixture_transport_disposition_evidence(
            fact=drain_fact,
            outcome="DELIVERED",
            observed_at=transport_result_time,
        ),
        commit_time=transport_result_time,
    )
    return ObserverAuthorizationCompositeEvidence(
        server_snapshot=server.store.snapshot,
        boundary_snapshots=tuple(boundary.store.snapshot for boundary in boundaries),
        default_deny_manifest=manifest,
        capability_evidence=capability_evidence,
        plan=plan,
        grant=grant,
        server_activation=server_activation,
        read_authorization_decision=read_authorization_decision,
        retained_read_authorization_cut=_retain_read_authorization_cut(
            read_authorization_decision
        ),
        read_authorization_exact_retry=read_authorization_exact_retry,
        boundary_preparations=preparations,
        boundary_activations=activations,
        release=release,
        drain_fact=drain_fact,
        drain_disposition=disposition,
    )


def _expect_rejection(
    label: str,
    operation: Callable[[], Any],
    accepted: list[str],
) -> None:
    try:
        operation()
    except ProbeError:
        accepted.append(label)
        return
    raise ProbeError(f"hostile case was accepted: {label}")


def _snapshot_with_transition(
    snapshot: ImmutableAuthoritySnapshot,
    index: int,
    replacement: AtomicTransitionRecord,
) -> ImmutableAuthoritySnapshot:
    prior = snapshot.transitions[index]
    objects = _tuple_map(snapshot.objects)
    content = _tuple_map(snapshot.content_bytes)
    objects.pop(_digest(prior))
    content.pop(_digest(prior))
    objects[_digest(replacement)] = replacement
    content[_digest(replacement)] = _canonical_bytes(replacement)
    transitions = list(snapshot.transitions)
    transitions[index] = replacement
    return replace(
        snapshot,
        objects=tuple(sorted(objects.items())),
        content_bytes=tuple(sorted(content.items())),
        transitions=tuple(transitions),
    )


def _prepared_fixture_from_evidence(
    evidence: ObserverAuthorizationCompositeEvidence,
) -> tuple[
    ObserverAuthorizationServer,
    tuple[tuple[AtomicAuthorityStore, BoundaryPreparationResult], ...],
    ObserverReadCapabilityEvidence,
]:
    prepared_snapshots = tuple(
        item
        for item in _tuple_map(evidence.server_snapshot.objects).values()
        if isinstance(item, ImmutableAuthoritySnapshot)
        and item.store_id.startswith("trusted-delivery-boundary:")
    )
    _require(
        len(prepared_snapshots) == len(evidence.plan.boundary_members),
        "prepared fixture boundary snapshot set mismatch",
    )
    prepared: list[tuple[AtomicAuthorityStore, BoundaryPreparationResult]] = []
    pending_server_snapshots: dict[str, ImmutableAuthoritySnapshot] = {}
    for snapshot in prepared_snapshots:
        objects = _tuple_map(snapshot.objects)
        transition = snapshot.transitions[-1]
        receipt = objects[transition.specialized_receipt_digests[1]]
        _require(
            isinstance(receipt, TrustedDeliveryBoundaryGrantEnforcementReceipt),
            "prepared fixture enforcement receipt is absent",
        )
        fact = objects[receipt.preparation_fact_digest]
        entry = objects[receipt.installed_entry_head_digest]
        _require(
            isinstance(fact, TrustedDeliveryBoundaryGrantPreparationFact)
            and isinstance(entry, TrustedDeliveryBoundaryGrantStateHead),
            "prepared fixture fact or entry is absent",
        )
        preparation = BoundaryPreparationResult(
            fact=fact,
            enforcement_receipt=receipt,
            installed_entry=entry,
        )
        prepared.append(
            (
                AtomicAuthorityStore._from_validated_counterfactual_snapshot_for_test(
                    snapshot,
                    trusted_clock_sample=(
                        _fixture_continuous_recovery_clock_sample(snapshot)
                    ),
                ),
                preparation,
            )
        )
        for item in objects.values():
            if (
                isinstance(item, ImmutableAuthoritySnapshot)
                and item.store_id == "observer-authorization-server"
                and item.state_digest == fact.server_pending_outer_head_digest
            ):
                pending_server_snapshots[_digest(item)] = item
    _require(
        len(pending_server_snapshots) == 1,
        "prepared fixture pending server snapshot is ambiguous",
    )
    server = ObserverAuthorizationServer()
    pending_server_snapshot = next(iter(pending_server_snapshots.values()))
    server.store = (
        AtomicAuthorityStore._from_validated_counterfactual_snapshot_for_test(
            pending_server_snapshot,
            trusted_clock_sample=(
                _fixture_continuous_recovery_clock_sample(pending_server_snapshot)
            ),
        )
    )
    return (
        server,
        tuple(
            sorted(
                prepared,
                key=lambda item: _canonical_bytes(
                    item[1].fact.boundary_member.identity
                ),
            )
        ),
        evidence.capability_evidence,
    )


def _snapshot_prefix(
    snapshot: ImmutableAuthoritySnapshot,
    transition_count: int,
) -> ImmutableAuthoritySnapshot:
    _require(
        0 < transition_count <= len(snapshot.transitions),
        "snapshot prefix transition count is outside history",
    )
    transitions = snapshot.transitions[:transition_count]
    required: set[str] = set()
    for transition in transitions:
        required.add(_digest(transition))
        required.add(transition.operation_commitment_digest)
        required.add(transition.installed_state_digest)
        if transition.prior_state_digest is not None:
            required.add(transition.prior_state_digest)
        required.add(transition.selector_digest)
        required.add(transition.generic_commit_digest)
        required.update(transition.specialized_receipt_digests)
        required.update(transition.co_committed_object_digests)
        if transition.deadline_intent_set_digest is not None:
            required.add(transition.deadline_intent_set_digest)
        operation_commitment = _tuple_map(snapshot.objects)[
            transition.operation_commitment_digest
        ]
        _require(
            isinstance(
                operation_commitment,
                AuthorityTransitionOperationCommitment,
            ),
            "snapshot prefix operation commitment is absent",
        )
        required.update(operation_commitment.receipt_free_object_digests)
    objects = _tuple_map(snapshot.objects)
    content = _tuple_map(snapshot.content_bytes)
    selected_objects = {digest: objects[digest] for digest in required}
    selected_content = {digest: content[digest] for digest in required}
    signed_digests = {transition.generic_commit_digest for transition in transitions}
    for transition in transitions:
        signed_digests.update(transition.specialized_receipt_digests)
    signed = _tuple_map(snapshot.signed_bytes)
    last = transitions[-1]
    prefix = replace(
        snapshot,
        snapshot_version=transition_count,
        state=objects[last.installed_state_digest],
        state_digest=last.installed_state_digest,
        objects=tuple(sorted(selected_objects.items())),
        content_bytes=tuple(sorted(selected_content.items())),
        signed_bytes=tuple(
            sorted((digest, signed[digest]) for digest in signed_digests)
        ),
        transitions=transitions,
        clock_sample_high_watermarks=(
            (last.commit_clock_incarnation, last.exact_commit_time),
        ),
    )
    _validate_atomic_snapshot(prefix)
    return prefix


def _validate_explicit_type_registry(
    evidence: ObserverAuthorizationCompositeEvidence,
) -> tuple[str, ...]:
    registry = _CANONICAL_ARTIFACT_TYPE_IDS
    _require(
        type(registry) is FrozenTypeRegistry,
        "canonical artifact registry is not frozen",
    )
    try:
        shape_view = registry.revalidated_shape_view()
    except ValueError as exc:
        raise ProbeError("canonical artifact registry shape was rejected") from exc
    registered_ids = tuple(type_id for type_id, _field_names in shape_view)
    _require(
        len(registered_ids) == len(set(registered_ids)),
        "canonical artifact type registry is not one-to-one",
    )
    reached: set[str] = set()

    def visit(value: Any) -> None:
        registered_type_id = registry.get(type(value))
        if registered_type_id is not None:
            snapshot_type_id, field_snapshot = _artifact_field_snapshot(value)
            _require(
                snapshot_type_id == registered_type_id,
                "staged artifact type ID changed during its snapshot",
            )
            reached.add(snapshot_type_id)
            for _field_name, field_value in field_snapshot:
                visit(field_value)
            return
        if type(value) is dict:
            for key, item in value.items():
                visit(key)
                visit(item)
            return
        if type(value) in (tuple, list):
            for item in value:
                visit(item)
            return
        _require(
            value is None or type(value) in (str, int, bool, bytes),
            "artifact registry closure reached a subclassed or unsupported value",
        )

    visit(evidence)
    _require(bool(reached), "artifact registry closure reached no staged types")
    return tuple(sorted(reached))


def _run_release_linearization_tests(
    evidence: ObserverAuthorizationCompositeEvidence,
) -> tuple[str, ...]:
    """Exercise the reservation gap and the sole atomic release linearization."""

    final_snapshot = evidence.boundary_snapshots[0]
    activation_transition_count = next(
        index
        for index, transition in enumerate(final_snapshot.transitions, start=1)
        if transition.transition_kind == "ACTIVATE_PREPARED_BOUNDARY_GRANT"
    )
    live_snapshot = _snapshot_prefix(
        final_snapshot,
        activation_transition_count,
    )
    live_state = live_snapshot.state
    _require(
        isinstance(live_state, TrustedDeliveryReleaseStateHead),
        "release linearization fixture lacks a live outer state",
    )
    member = evidence.plan.boundary_members[0]
    preparation = evidence.boundary_preparations[0]
    activation = evidence.boundary_activations[0]
    payload = evidence.release.outbox_item.complete_payload
    release_context = evidence.release.pending_reservation.release_recipient_context
    expected_transport_context = (
        evidence.release.pending_reservation.expected_release_transport_context
    )
    release_idempotency_key = (
        evidence.release.pending_reservation.release_cas.release_idempotency_key
    )
    reservation_time = (
        evidence.release.pending_reservation.grant_currentness_evidence.verified_at
    )
    outbox_commit_time = (
        evidence.release.reservation.grant_currentness_evidence.verified_at
    )

    def fresh_live_boundary() -> tuple[
        TrustedDeliveryBoundary,
        _SyntheticRecoveryAuthority,
    ]:
        boundary = TrustedDeliveryBoundary(member)
        (
            boundary.store,
            recovery_authority,
        ) = AtomicAuthorityStore._enroll_validated_counterfactual_snapshot_for_test(
            live_snapshot,
            trusted_clock_sample=(
                _fixture_continuous_recovery_clock_sample(live_snapshot)
            ),
        )
        boundary._persistence_recovery_authority = recovery_authority
        return boundary, recovery_authority

    def create_pending(
        boundary: TrustedDeliveryBoundary,
        *,
        selected_payload: bytes = payload,
        selected_idempotency_key: str = release_idempotency_key,
    ) -> TrustedDeliveryReleaseReservation:
        return boundary.create_reservation(
            activation=activation,
            payload=selected_payload,
            read_scope=member.read_scope,
            boundary_membership=member.scope_membership,
            read_authorization_decision=evidence.read_authorization_decision,
            retained_authorization_cut=evidence.retained_read_authorization_cut,
            release_recipient_context=release_context,
            expected_release_transport_context=expected_transport_context,
            expected_release_context_artifact_digest=(
                release_recipient_artifact_digest(release_context)
            ),
            release_idempotency_key=selected_idempotency_key,
            commit_time=reservation_time,
        )

    boundary, recovery_authority = fresh_live_boundary()
    pending = create_pending(boundary)
    pending_snapshot = boundary.store.snapshot
    pending_root = boundary.store.persistence_root
    zombie_writer = boundary.store
    _validate_atomic_snapshot(pending_snapshot)
    pending_state = pending_snapshot.state
    _require(
        isinstance(pending_state, TrustedDeliveryReleaseStateHead)
        and pending_state.next_release_sequence == live_state.next_release_sequence
        and pending_state.next_output_slot == live_state.next_output_slot
        and pending_state.used_release_identities == live_state.used_release_identities
        and pending_state.consumed_read_decision_digests
        == live_state.consumed_read_decision_digests
        and pending_state.installed_release_counter_state_digests
        == live_state.installed_release_counter_state_digests
        and pending_state.used_output_slots == live_state.used_output_slots
        and pending_state.outbox_items == live_state.outbox_items
        and boundary.entry(pending.full_boundary_key).pending_reservation_digests
        == (_digest(pending),),
        "crash-after-reservation state consumed authority or exposed an outbox",
    )
    witnesses = ["reservation_crash_recovery_preserves_only_pending_fence"]

    recovery_admission = recovery_authority.issue_admission(
        trusted_recovery_clock_sample=(
            _fixture_continuous_recovery_clock_sample(pending_snapshot)
        ),
        writer_exclusive_not_after=10_000,
    )
    recovered = TrustedDeliveryBoundary(member)
    recovered.store = AtomicAuthorityStore.recover(
        pending_snapshot,
        admission=recovery_admission,
    )
    recovered._persistence_recovery_authority = recovery_authority
    _require(
        recovered.store.persistence_root == pending_root,
        "recovery changed the exact durable pending root",
    )
    try:
        zombie_writer.set_trusted_clock_for_test(
            _fixture_continuous_recovery_clock_sample(pending_snapshot)
        )
    except ProbeError:
        pass
    else:
        raise ProbeError("recovery left the predecessor writer capability live")
    retry_transition_count = len(recovered.store.snapshot.transitions)
    exact_retry = create_pending(recovered)
    _require(
        exact_retry == pending
        and len(recovered.store.snapshot.transitions) == retry_transition_count,
        "exact reservation retry changed state or artifact identity",
    )
    witnesses.append("reservation_exact_retry_is_state_free")
    try:
        AtomicAuthorityStore.recover(
            pending_snapshot,
            admission=recovery_admission,
        )
    except ProbeError:
        pass
    else:
        raise ProbeError("one-use recovery admission was replayable")
    witnesses.append("recovery_rotates_writer_and_consumes_admission")

    try:
        create_pending(
            recovered,
            selected_payload=b"distinct-concurrent-sibling-payload",
            selected_idempotency_key=_uuid_for(
                ("distinct-concurrent-release-sibling",)
            ),
        )
    except ProbeError:
        pass
    else:
        raise ProbeError("exclusive pending fence accepted a distinct sibling")
    _require(
        recovered.store.snapshot == pending_snapshot,
        "rejected reservation sibling changed durable state",
    )
    witnesses.append("reservation_distinct_concurrent_sibling_rejected")

    foreign_preparation = evidence.boundary_preparations[1]
    foreign_activation = evidence.boundary_activations[1]
    for label, selected_preparation, selected_activation in (
        (
            "foreign_preparation_receipt",
            foreign_preparation,
            activation,
        ),
        (
            "foreign_activation_receipt",
            preparation,
            foreign_activation,
        ),
    ):
        substituted_boundary = TrustedDeliveryBoundary(member)
        substituted_boundary.store = (
            AtomicAuthorityStore._from_validated_counterfactual_snapshot_for_test(
                pending_snapshot,
                trusted_clock_sample=(
                    _fixture_continuous_recovery_clock_sample(pending_snapshot)
                ),
            )
        )
        try:
            substituted_boundary.release_to_outbox(
                reservation=pending,
                preparation=selected_preparation,
                activation=selected_activation,
                payload=payload,
                commit_time=outbox_commit_time,
            )
        except ProbeError:
            pass
        else:
            raise ProbeError(f"atomic outbox commit accepted {label.replace('_', ' ')}")
        _require(
            substituted_boundary.store.snapshot == pending_snapshot,
            f"rejected {label.replace('_', ' ')} changed durable state",
        )
        witnesses.append(f"{label}_substitution_rejected")

    terminal_boundary = TrustedDeliveryBoundary(member)
    terminal_boundary.store = (
        AtomicAuthorityStore._from_validated_counterfactual_snapshot_for_test(
            pending_snapshot,
            trusted_clock_sample=(
                _fixture_continuous_recovery_clock_sample(pending_snapshot)
            ),
        )
    )
    terminal_prior_entry = terminal_boundary.entry(pending.full_boundary_key)
    _require(
        type(terminal_prior_entry) is TrustedDeliveryBoundaryGrantStateHead,
        "terminal fixture predecessor is absent",
    )
    terminal = terminal_boundary.terminalize(
        key=pending.full_boundary_key,
        cause="LOCAL_FIXED_DEADLINE_EXPIRED",
        server=None,
        server_terminal=None,
        renewal_fence=None,
        commit_time=terminal_prior_entry.deadline.boundary_release_not_after,
    )
    terminal_state = terminal_boundary.head
    terminal_entry = terminal_boundary.entry(pending.full_boundary_key)
    _require(
        terminal.fact.canceled_reservation_digests == (_digest(pending),)
        and not terminal_entry.pending_reservation_digests
        and _digest(pending) in terminal_entry.canceled_reservation_tombstones
        and not terminal_state.consumed_read_decision_digests
        and not terminal_state.installed_release_counter_state_digests
        and not terminal_state.outbox_items
        and terminal_entry.installed_release_counter_state_digest is None,
        "terminal-after-reservation confused a canceled intent with a release",
    )
    _validate_atomic_snapshot(terminal_boundary.store.snapshot)
    witnesses.append("terminal_cancels_intent_without_release_or_quota_effect")

    terminal_server = ObserverAuthorizationServer()
    terminal_server.store = (
        AtomicAuthorityStore._from_validated_counterfactual_snapshot_for_test(
            evidence.server_snapshot,
            trusted_clock_sample=(
                _fixture_continuous_recovery_clock_sample(evidence.server_snapshot)
            ),
        )
    )
    terminal_server_entry = terminal_server.entry(evidence.plan.stable_registry_key)
    _require(
        type(terminal_server_entry) is ObserverGrantLedgerHead,
        "server-expiry fixture lacks its current grant head",
    )
    server_terminal = terminal_server.terminate(
        evidence.plan.stable_registry_key,
        terminal_reason="EXPIRED",
        actor_or_event="trusted-clock-expiry",
        policy_rule_digest=_SERVER_EXPIRY_POLICY_RULE_DIGEST,
        policy_inputs_digest=_SERVER_EXPIRY_POLICY_INPUTS_DIGEST,
        authority_source_receipt_digest=(
            _SERVER_EXPIRY_AUTHORITY_SOURCE_RECEIPT_DIGEST
        ),
        commit_time=terminal_server_entry.effective_server_not_after,
        expiry=True,
    )
    server_terminal_boundary, _unused_recovery_authority = fresh_live_boundary()
    server_terminal_boundary.terminalize(
        key=activation.installed_entry.full_boundary_key,
        cause="SERVER_TERMINAL",
        server=terminal_server,
        server_terminal=server_terminal,
        renewal_fence=None,
        commit_time=_fixture_continuous_recovery_clock_sample(
            server_terminal_boundary.store.snapshot
        ),
    )
    _validate_atomic_snapshot(server_terminal_boundary.store.snapshot)
    witnesses.append("server_expiry_terminal_anchor_closes_exact_boundary")

    mixed_terminal_boundary, _unused_recovery_authority = fresh_live_boundary()
    mixed_terminal_snapshot = mixed_terminal_boundary.store.snapshot
    mixed_terminal = replace(
        server_terminal,
        transition_fact=replace(
            server_terminal.transition_fact,
            actor_or_event="forged-terminal-wrapper",
        ),
    )
    try:
        mixed_terminal_boundary.terminalize(
            key=activation.installed_entry.full_boundary_key,
            cause="SERVER_TERMINAL",
            server=terminal_server,
            server_terminal=mixed_terminal,
            renewal_fence=None,
            commit_time=_fixture_continuous_recovery_clock_sample(
                mixed_terminal_snapshot
            ),
        )
    except ProbeError:
        pass
    else:
        raise ProbeError("boundary admitted a mixed server-terminal wrapper")
    _require(
        mixed_terminal_boundary.store.snapshot == mixed_terminal_snapshot,
        "rejected mixed server-terminal wrapper changed durable state",
    )
    witnesses.append("mixed_server_terminal_wrapper_is_rejected")

    committing_boundary = TrustedDeliveryBoundary(member)
    committing_boundary.store = (
        AtomicAuthorityStore._from_validated_counterfactual_snapshot_for_test(
            pending_snapshot,
            trusted_clock_sample=(
                _fixture_continuous_recovery_clock_sample(pending_snapshot)
            ),
        )
    )
    release = committing_boundary.release_to_outbox(
        reservation=pending,
        preparation=preparation,
        activation=activation,
        payload=payload,
        commit_time=outbox_commit_time,
    )
    committed_state = committing_boundary.head
    committed_entry = committing_boundary.entry(pending.full_boundary_key)
    _require(
        release.pending_reservation == pending
        and release.reservation.grant_currentness_evidence.boundary_state_head_digest
        == _digest(pending_state)
        and release.reservation.grant_currentness_evidence.grant_entry_head_digest
        == _digest(
            AtomicAuthorityStore._from_validated_counterfactual_snapshot_for_test(
                pending_snapshot,
                trusted_clock_sample=(
                    _fixture_continuous_recovery_clock_sample(pending_snapshot)
                ),
            ).object(
                _tuple_map(committing_boundary.grant_map(pending_state).entries)[
                    _digest(pending.full_boundary_key)
                ],
                TrustedDeliveryBoundaryGrantStateHead,
            )
        )
        and release.reservation.grant_currentness_evidence.boundary_state_head_digest
        != pending.grant_currentness_evidence.boundary_state_head_digest
        and committed_state.consumed_read_decision_digests
        == (pending.read_authorization_decision_digest,)
        and _tuple_map(committed_state.installed_release_counter_state_digests)[
            pending.read_authorization_decision_digest
        ]
        == release.reservation.release_cas.next_release_counter_state_digest
        == committed_entry.installed_release_counter_state_digest
        and len(committed_state.outbox_items) == 1
        and not committed_entry.pending_reservation_digests,
        "atomic outbox commit did not co-install the fresh CAS successor and "
        "exact outbox",
    )
    _validate_atomic_snapshot(committing_boundary.store.snapshot)
    committed_transition_count = len(committing_boundary.store.snapshot.transitions)
    release_retry = committing_boundary.release_to_outbox(
        reservation=pending,
        preparation=preparation,
        activation=activation,
        payload=payload,
        commit_time=outbox_commit_time + 1,
    )
    _require(
        release_retry == release
        and len(committing_boundary.store.snapshot.transitions)
        == committed_transition_count,
        "exact outbox retry changed the atomic result or durable state",
    )
    witnesses.append("atomic_release_commit_and_exact_retry_share_one_result")

    first_dispatch_context = evidence.drain_fact.dispatch_context
    destination_cut = evidence.drain_fact.expected_dispatch_destination_cut
    first_attempt = committing_boundary.start_external_drain(
        release=release,
        actual_dispatch_payload=release.outbox_item.complete_payload,
        dispatch_context=first_dispatch_context,
        expected_dispatch_destination_cut=destination_cut,
        expected_dispatch_context_artifact_digest=(
            dispatch_artifact_digest(first_dispatch_context)
        ),
        receiver_dedup_retry_proof=None,
        commit_time=first_dispatch_context.verified_at,
    )
    started_dispatch_snapshot = committing_boundary.store.snapshot

    def branch_from_started_dispatch() -> TrustedDeliveryBoundary:
        branch = TrustedDeliveryBoundary(member)
        branch.store = (
            AtomicAuthorityStore._from_validated_counterfactual_snapshot_for_test(
                started_dispatch_snapshot,
                trusted_clock_sample=(
                    _fixture_continuous_recovery_clock_sample(started_dispatch_snapshot)
                ),
            )
        )
        return branch

    dispatch_deadline = first_dispatch_context.exclusive_not_after
    _require(
        dispatch_deadline
        == first_attempt.expected_dispatch_destination_cut.exclusive_not_after
        == branch_from_started_dispatch()
        .entry(first_attempt.full_boundary_key)
        .deadline.boundary_release_not_after,
        "transport-race fixture does not share one exclusive deadline",
    )

    terminal_first = branch_from_started_dispatch()
    terminal_first.terminalize(
        key=first_attempt.full_boundary_key,
        cause="LOCAL_FIXED_DEADLINE_EXPIRED",
        server=None,
        server_terminal=None,
        renewal_fence=None,
        commit_time=dispatch_deadline,
    )
    terminal_first_snapshot = terminal_first.store.snapshot
    try:
        terminal_first.enqueue_external_transport_for_test(
            fact=first_attempt,
            exact_payload=release.outbox_item.complete_payload,
            enqueue_time=dispatch_deadline,
        )
    except ProbeError:
        pass
    else:
        raise ProbeError("terminal-first transport race emitted bytes")
    _require(
        terminal_first.store.snapshot == terminal_first_snapshot,
        "terminal-first rejected enqueue changed durable state",
    )
    try:
        terminal_first.store.require_external_transport_enqueue_for_test(first_attempt)
    except ProbeError:
        pass
    else:
        raise ProbeError("terminal-first transport race retained an enqueue")
    witnesses.append("terminal_first_fences_physical_enqueue_atomically")

    enqueue_first = branch_from_started_dispatch()
    enqueue_record = enqueue_first.enqueue_external_transport_for_test(
        fact=first_attempt,
        exact_payload=release.outbox_item.complete_payload,
        enqueue_time=first_dispatch_context.verified_at,
    )
    try:
        enqueue_first.enqueue_external_transport_for_test(
            fact=first_attempt,
            exact_payload=release.outbox_item.complete_payload,
            enqueue_time=first_dispatch_context.verified_at,
        )
    except ProbeError:
        pass
    else:
        raise ProbeError("physical enqueue admitted an exact replay")
    _require(
        enqueue_first.store.require_external_transport_enqueue_for_test(first_attempt)
        == enqueue_record
        and enqueue_record.queue_sequence == 1,
        "rejected physical-enqueue replay changed the exact queue record",
    )
    enqueue_first.terminalize(
        key=first_attempt.full_boundary_key,
        cause="LOCAL_FIXED_DEADLINE_EXPIRED",
        server=None,
        server_terminal=None,
        renewal_fence=None,
        commit_time=dispatch_deadline,
    )
    enqueue_first_terminal_entry = enqueue_first.entry(first_attempt.full_boundary_key)
    _require(
        enqueue_first.store.require_external_transport_enqueue_for_test(first_attempt)
        == enqueue_record
        and type(enqueue_first_terminal_entry) is TrustedDeliveryBoundaryGrantStateHead
        and enqueue_first_terminal_entry.phase == "TERMINAL_BOUNDARY_GRANT"
        and _digest(first_attempt)
        in enqueue_first_terminal_entry.active_drain_fact_digests,
        "enqueue-first transport race lost or duplicated the linearized send",
    )
    witnesses.append("enqueue_first_survives_terminal_as_one_exact_record")

    exact_deadline = branch_from_started_dispatch()
    exact_deadline_snapshot = exact_deadline.store.snapshot
    try:
        exact_deadline.enqueue_external_transport_for_test(
            fact=first_attempt,
            exact_payload=release.outbox_item.complete_payload,
            enqueue_time=dispatch_deadline,
        )
    except ProbeError:
        pass
    else:
        raise ProbeError("exclusive transport deadline was treated as inclusive")
    _require(
        exact_deadline.store.snapshot == exact_deadline_snapshot,
        "exact-deadline rejected enqueue changed durable state",
    )
    try:
        exact_deadline.store.require_external_transport_enqueue_for_test(first_attempt)
    except ProbeError:
        pass
    else:
        raise ProbeError("exact-deadline rejection retained an enqueue record")
    witnesses.append("enqueue_at_exclusive_deadline_is_fail_closed")

    committing_boundary.enqueue_external_transport_for_test(
        fact=first_attempt,
        exact_payload=release.outbox_item.complete_payload,
        enqueue_time=first_dispatch_context.verified_at,
    )
    started_dispatch_snapshot = committing_boundary.store.snapshot
    for invalid_outcome, invalid_evidence in (
        (
            "AMBIGUOUS_AFTER_EXTERNAL_TRANSPORT",
            hashlib.sha256(b"forged-definitive-evidence-for-unknown").hexdigest(),
        ),
        ("UNKNOWN_TRANSPORT_RESULT", None),
    ):
        try:
            committing_boundary.resolve_external_drain(
                fact=first_attempt,
                outcome=invalid_outcome,
                transport_evidence=invalid_evidence,
                commit_time=first_dispatch_context.verified_at + 1,
            )
        except ProbeError:
            pass
        else:
            raise ProbeError(
                "dispatch disposition accepted an unknown outcome or "
                "definitive evidence on an ambiguous outcome"
            )
        _require(
            committing_boundary.store.snapshot == started_dispatch_snapshot,
            "rejected dispatch disposition changed durable state",
        )
    witnesses.append(
        "ambiguous_dispatch_rejects_definitive_evidence_and_unknown_outcome"
    )
    ambiguous_disposition = committing_boundary.resolve_external_drain(
        fact=first_attempt,
        outcome="AMBIGUOUS_AFTER_EXTERNAL_TRANSPORT",
        transport_evidence=None,
        commit_time=first_dispatch_context.verified_at + 1,
    )
    retry_proof = seal_receiver_deduplication_retry_proof(
        SyntheticReceiverDeduplicationRetryProof(
            provenance_kind=("SYNTHETIC_AUTHENTICATED_RECEIVER_DEDUPLICATION_RETRY"),
            stable_outbox_item_id=release.outbox_item.stable_item_id,
            committed_outbox_artifact_digest=(
                committed_outbox_artifact_digest(
                    release.outbox_item.committed_bridge_outbox_artifact
                )
            ),
            transport_idempotency_key=release.outbox_item.idempotency_key,
            prior_attempt_identity=first_attempt.attempt_identity,
            prior_disposition_digest=_digest(ambiguous_disposition),
            stable_destination_digest=dispatch_stable_destination_digest(
                destination_cut
            ),
            receiver_deduplication_state_digest=hashlib.sha256(
                b"synthetic-receiver-deduplication-state-after-unknown"
            ).hexdigest(),
            delivery_outcome="UNKNOWN_NO_SUCCESS_INFERRED",
            semantic_proof_digest="",
            fixture_authentication_tag="",
        )
    )
    second_attempt_sequence = first_attempt.attempt_sequence + 1
    second_attempt_identity = _uuid_for(
        (
            release.outbox_item.attempt_namespace,
            second_attempt_sequence,
            committing_boundary.head.next_attempt_sequence,
        )
    )
    retry_transport_gate_epoch = committing_boundary.store.snapshot.snapshot_version
    retry_destination_cut = replace(
        destination_cut,
        transport_gate_state_digest="0" * 64,
        transport_gate_epoch=retry_transport_gate_epoch,
    )
    retry_destination_cut = replace(
        retry_destination_cut,
        transport_gate_state_digest=dispatch_transport_gate_state_digest(
            retry_destination_cut
        ),
    )
    retry_dispatch_context = seal_dispatch_context(
        replace(
            first_dispatch_context,
            dispatch_verification_event_id=_uuid_for(
                (
                    "dispatch-verification",
                    release.outbox_item.stable_item_id,
                    second_attempt_sequence,
                )
            ),
            dispatch_attempt_id=second_attempt_identity,
            destination_cut_digest=dispatch_destination_cut_digest(
                retry_destination_cut
            ),
            transport_gate_state_digest=(
                retry_destination_cut.transport_gate_state_digest
            ),
            transport_gate_epoch=retry_destination_cut.transport_gate_epoch,
            verified_at=first_dispatch_context.verified_at + 2,
            semantic_context_digest="",
            fixture_authentication_tag="",
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    retry_attempt = committing_boundary.start_external_drain(
        release=release,
        actual_dispatch_payload=release.outbox_item.complete_payload,
        dispatch_context=retry_dispatch_context,
        expected_dispatch_destination_cut=retry_destination_cut,
        expected_dispatch_context_artifact_digest=(
            dispatch_artifact_digest(retry_dispatch_context)
        ),
        receiver_dedup_retry_proof=retry_proof,
        commit_time=retry_dispatch_context.verified_at,
    )
    committing_boundary.enqueue_external_transport_for_test(
        fact=retry_attempt,
        exact_payload=release.outbox_item.complete_payload,
        enqueue_time=retry_dispatch_context.verified_at,
    )
    _require(
        ambiguous_disposition.outcome == "AMBIGUOUS_AFTER_EXTERNAL_TRANSPORT"
        and ambiguous_disposition.authenticated_transport_evidence_digest is None
        and not ambiguous_disposition.no_resend_right
        and retry_proof.delivery_outcome == "UNKNOWN_NO_SUCCESS_INFERRED"
        and retry_attempt.attempt_identity != first_attempt.attempt_identity
        and retry_attempt.attempt_sequence == first_attempt.attempt_sequence + 1
        and retry_attempt.stable_item_id == first_attempt.stable_item_id
        and retry_attempt.idempotency_key == first_attempt.idempotency_key
        and retry_attempt.actual_dispatch_payload
        == first_attempt.actual_dispatch_payload
        and retry_attempt.dispatch_context.destination_cut_digest
        != first_attempt.dispatch_context.destination_cut_digest
        and dispatch_stable_destination_digest(
            retry_attempt.expected_dispatch_destination_cut
        )
        == dispatch_stable_destination_digest(
            first_attempt.expected_dispatch_destination_cut
        )
        and retry_attempt.dispatch_context.transport_gate_epoch
        > first_attempt.dispatch_context.transport_gate_epoch
        and committing_boundary.head.used_attempt_identities[-2:]
        == (first_attempt.attempt_identity, retry_attempt.attempt_identity),
        "unknown external outcome retry changed bytes/destination/idempotency, "
        "reused an attempt, or inferred success",
    )
    _validate_atomic_snapshot(committing_boundary.store.snapshot)
    witnesses.append(
        "unknown_delivery_retry_requires_receiver_dedup_and_stable_identity"
    )

    first_attempt = _uuid_for(("minimal-attempt-state", 1))
    second_attempt = _uuid_for(("minimal-attempt-state", 2))
    attempt_state = _append_unique_attempt_identity((), first_attempt)
    attempt_state = _append_unique_attempt_identity(
        attempt_state,
        second_attempt,
    )
    _require(
        attempt_state == (first_attempt, second_attempt),
        "two-item attempt identity fixture duplicated a prior identity",
    )
    witnesses.append("two_distinct_outbox_attempt_identities_append_once")
    return tuple(witnesses)


def _run_hostile_tests(
    evidence: ObserverAuthorizationCompositeEvidence,
) -> tuple[str, ...]:
    accepted: list[str] = []

    class IntegerAlias(int):
        pass

    class StringAlias(str):
        pass

    class BytesAlias(bytes):
        pass

    class TupleAlias(tuple):
        pass

    class ListAlias(list):
        pass

    class DictAlias(dict):
        pass

    class SetAlias(set):
        pass

    class FrozenSetAlias(frozenset):
        pass

    class StringClosedEnum(str, Enum):
        SUBSCRIBE = "subscribe"

    @dataclass(frozen=True)
    class ObserverDescriptorAlias(ObserverDescriptor):
        pass

    _expect_rejection(
        "canonical_float_rejected",
        lambda: _canonical_bytes(0.0),
        accepted,
    )
    _expect_rejection(
        "canonical_oversize_integer_rejected",
        lambda: _canonical_bytes(MAX_SAFE_INTEGER + 1),
        accepted,
    )
    _expect_rejection(
        "canonical_non_string_map_key_rejected",
        lambda: _canonical_bytes({1: "coercion-forbidden"}),
        accepted,
    )
    exact_descriptor = next(
        item
        for item in _tuple_map(evidence.server_snapshot.objects).values()
        if type(item) is ObserverDescriptor
    )
    _descriptor_type_id, descriptor_snapshot = _artifact_field_snapshot(
        exact_descriptor
    )
    descriptor_alias = ObserverDescriptorAlias(**dict(descriptor_snapshot))

    def reject_registered_descriptor_getattribute_mutation() -> None:
        class_dict = type.__getattribute__(ObserverDescriptor, "__dict__")
        had_own_getattribute = "__getattribute__" in class_dict
        original_getattribute = class_dict.get("__getattribute__")

        def hostile_getattribute(_self: Any, _name: str) -> Any:
            raise AssertionError("hostile descriptor hook executed")

        type.__setattr__(
            ObserverDescriptor,
            "__getattribute__",
            hostile_getattribute,
        )
        try:
            _artifact_field_snapshot(exact_descriptor)
        finally:
            if had_own_getattribute:
                type.__setattr__(
                    ObserverDescriptor,
                    "__getattribute__",
                    original_getattribute,
                )
            else:
                type.__delattr__(ObserverDescriptor, "__getattribute__")

    exact_type_hostiles: tuple[tuple[str, Callable[[], Any]], ...] = (
        (
            "registered_artifact_getattribute_mutation_rejected_without_hook",
            reject_registered_descriptor_getattribute_mutation,
        ),
        (
            "canonical_integer_subclass_rejected",
            lambda: _canonical_bytes(IntegerAlias(1)),
        ),
        (
            "canonical_string_subclass_rejected",
            lambda: _canonical_bytes(StringAlias("observer-a")),
        ),
        (
            "canonical_bytes_subclass_rejected",
            lambda: _canonical_bytes(BytesAlias(b"observer")),
        ),
        (
            "canonical_tuple_subclass_rejected",
            lambda: _canonical_bytes(TupleAlias(("observer-a",))),
        ),
        (
            "canonical_list_subclass_rejected",
            lambda: _canonical_bytes(ListAlias(["observer-a"])),
        ),
        (
            "canonical_dict_subclass_rejected",
            lambda: _canonical_bytes(DictAlias(observer="a")),
        ),
        (
            "canonical_set_rejected",
            lambda: _canonical_bytes(SetAlias({"observer-a"})),
        ),
        (
            "canonical_frozenset_rejected",
            lambda: _canonical_bytes(FrozenSetAlias({"observer-a"})),
        ),
        (
            "canonical_mapping_proxy_rejected",
            lambda: _canonical_bytes(MappingProxyType({"observer": "a"})),
        ),
        (
            "canonical_string_enum_rejected",
            lambda: _canonical_bytes(StringClosedEnum.SUBSCRIBE),
        ),
        (
            "canonical_dataclass_subclass_rejected",
            lambda: _digest(descriptor_alias),
        ),
        (
            "canonical_nested_integer_subclass_rejected",
            lambda: _digest(
                replace(
                    exact_descriptor,
                    descriptor_revision=IntegerAlias(1),
                )
            ),
        ),
        (
            "canonical_nested_string_subclass_rejected",
            lambda: _digest(
                replace(
                    exact_descriptor,
                    responder_principal=StringAlias(SERVER_PRINCIPAL),
                )
            ),
        ),
        (
            "canonical_nested_tuple_subclass_rejected",
            lambda: _digest(
                replace(
                    exact_descriptor,
                    allowed_boundary_member_identities=TupleAlias(
                        exact_descriptor.allowed_boundary_member_identities
                    ),
                )
            ),
        ),
        (
            "safe_integer_subclass_rejected",
            lambda: _require(
                _safe_int(IntegerAlias(1)),
                "integer subclass must not be JSON-safe",
            ),
        ),
        (
            "hex_string_subclass_rejected",
            lambda: _require(
                _is_hex64(StringAlias("0" * 64)),
                "string subclass must not be a canonical digest",
            ),
        ),
        (
            "immutable_scalar_subclass_rejected",
            lambda: _assert_deeply_immutable(StringAlias("observer-a")),
        ),
        (
            "immutable_dataclass_subclass_rejected",
            lambda: _assert_deeply_immutable(descriptor_alias),
        ),
        (
            "canonical_surrogate_string_rejected",
            lambda: _canonical_bytes("\ud800"),
        ),
        (
            "canonical_json_surrogate_string_rejected",
            lambda: _canonical_json_bytes({"value": "\ud800"}),
        ),
        (
            "tuple_list_type_erasure_collision_rejected",
            lambda: _require(
                _canonical_bytes(("observer-a",)) == _canonical_bytes(["observer-a"]),
                "tuple and list canonical bytes are type-separated",
            ),
        ),
        (
            "bytes_mapping_type_erasure_collision_rejected",
            lambda: _require(
                _canonical_bytes(b"observer")
                == _canonical_bytes(
                    {
                        "$ncp_canonical_kind": "bytes",
                        "hex": b"observer".hex(),
                    }
                ),
                "bytes and caller mapping canonical bytes are type-separated",
            ),
        ),
        (
            "artifact_mapping_type_erasure_collision_rejected",
            lambda: _require(
                _canonical_bytes(exact_descriptor)
                == _canonical_bytes(_normalize(exact_descriptor)),
                "artifact and caller mapping canonical bytes are type-separated",
            ),
        ),
    )
    for label, operation in exact_type_hostiles:
        _expect_rejection(label, operation, accepted)
    spoof_type = dataclass(frozen=True)(
        type(
            "ObserverGrant",
            (),
            {"__annotations__": {"marker": str}},
        )
    )
    spoof = spoof_type(marker="same-name-type-spoof")
    _expect_rejection(
        "unregistered_same_name_type_rejected",
        lambda: _canonical_bytes(spoof),
        accepted,
    )
    _expect_rejection(
        "mutable_staged_collection_rejected",
        lambda: _assert_deeply_immutable([1]),
        accepted,
    )

    mapping = evidence.plan.boundary_members[0].clock_mapping
    _expect_rejection(
        "clock_mapping_zero_denominator_rejected",
        lambda: _validate_mapping(replace(mapping, minimum_rate_denominator=0)),
        accepted,
    )
    _expect_rejection(
        "clock_mapping_untrusted_source_rejected",
        lambda: _validate_mapping(replace(mapping, source_receipt_current=False)),
        accepted,
    )
    _expect_rejection(
        "clock_mapping_bad_digest_rejected",
        lambda: _validate_mapping(replace(mapping, qualification_digest="opaque")),
        accepted,
    )
    _expect_rejection(
        "clock_mapping_zero_qualification_digest_rejected",
        lambda: _validate_mapping(replace(mapping, qualification_digest="0" * 64)),
        accepted,
    )
    _expect_rejection(
        "clock_mapping_zero_source_receipt_digest_rejected",
        lambda: _validate_mapping(replace(mapping, source_receipt_digest="0" * 64)),
        accepted,
    )
    _expect_rejection(
        "signed_artifact_zero_security_state_rejected",
        lambda: _signed_artifact(
            exact_descriptor,
            signer_principal=SERVER_PRINCIPAL,
            signing_key_id=SERVER_KEY_ID,
            security_state_digest="0" * 64,
        ),
        accepted,
    )
    _expect_rejection(
        "authority_store_zero_security_state_rejected",
        lambda: AtomicAuthorityStore.enroll(
            store_id="hostile-zero-security-authority-store",
            authority_principal=SERVER_PRINCIPAL,
            authority_key_id=SERVER_KEY_ID,
            security_state_digest="0" * 64,
            clock_incarnation=SERVER_CLOCK_1,
            writer_exclusive_not_after=10,
        ),
        accepted,
    )
    _expect_rejection(
        "clock_mapping_reverse_extrapolation_rejected",
        lambda: _map_lower(mapping, mapping.coordinator_reference - 1),
        accepted,
    )
    _expect_rejection(
        "clock_mapping_source_horizon_rejected",
        lambda: _map_upper(mapping, mapping.source_applicability_end + 1),
        accepted,
    )
    _expect_rejection(
        "clock_mapping_duration_horizon_rejected",
        lambda: _map_duration_upper(
            mapping,
            2,
            source_anchor=mapping.source_applicability_end,
        ),
        accepted,
    )
    _expect_rejection(
        "checked_integer_overflow_rejected",
        lambda: _checked_add(MAX_SAFE_INTEGER, 1),
        accepted,
    )
    _expect_rejection(
        "unknown_server_phase_transition_rejected",
        lambda: _server_transition_guard("UNKNOWN", "ABSENT", "LIVE"),
        accepted,
    )
    _expect_rejection(
        "server_phase_skip_rejected",
        lambda: _server_transition_guard(
            "ACTIVATE_PENDING_GRANT",
            "ABSENT",
            "LIVE",
        ),
        accepted,
    )
    _expect_rejection(
        "unknown_boundary_phase_transition_rejected",
        lambda: _boundary_transition_guard(
            "UNKNOWN",
            "ABSENT",
            "LIVE_BOUNDARY_GRANT",
        ),
        accepted,
    )
    _expect_rejection(
        "boundary_phase_skip_rejected",
        lambda: _boundary_transition_guard(
            "ACTIVATE_PREPARED_BOUNDARY_GRANT",
            "ABSENT",
            "LIVE_BOUNDARY_GRANT",
        ),
        accepted,
    )
    _expect_rejection(
        "unknown_store_schema_rejected",
        lambda: _receipt_schema(
            "forged-store",
            "ATTACH_NEW_GRANT_LINEAGE",
        ),
        accepted,
    )
    _expect_rejection(
        "unsupported_reattach_schema_rejected",
        lambda: _receipt_schema(
            "observer-authorization-server",
            "REATTACH_FROM_TERMINAL_GRANT",
        ),
        accepted,
    )
    _expect_rejection(
        "unsupported_bulk_terminal_schema_rejected",
        lambda: _receipt_schema(
            evidence.boundary_snapshots[0].store_id,
            "BULK_TERMINATE_BOUNDARY_GRANTS",
        ),
        accepted,
    )
    _expect_rejection(
        "unsupported_boundary_restart_schema_rejected",
        lambda: _receipt_schema(
            evidence.boundary_snapshots[0].store_id,
            "BRIDGE_BOUNDARY_CLOCK_RESTART",
        ),
        accepted,
    )

    def reject_grant_substitution(
        label: str,
        mutated_grant: ObserverGrant,
    ) -> None:
        _expect_rejection(
            label,
            lambda: _validate_plan_and_grant(
                evidence.plan,
                mutated_grant,
                _full_key(evidence.plan, mutated_grant),
            ),
            accepted,
        )

    reject_grant_substitution(
        "plan_grant_session_substitution_rejected",
        replace(
            evidence.grant,
            session_generation=_uuid_for(("forged-session-generation",)),
        ),
    )
    reject_grant_substitution(
        "plan_grant_descriptor_substitution_rejected",
        replace(
            evidence.grant,
            descriptor_digest=hashlib.sha256(b"forged-descriptor").hexdigest(),
        ),
    )
    reject_grant_substitution(
        "plan_grant_privacy_substitution_rejected",
        replace(
            evidence.grant,
            privacy_policy_digest=hashlib.sha256(b"forged-privacy").hexdigest(),
        ),
    )
    reject_grant_substitution(
        "plan_grant_security_substitution_rejected",
        replace(
            evidence.grant,
            security_state_digest=SECURITY_STATE_DIGEST_2,
        ),
    )
    reject_grant_substitution(
        "plan_grant_security_epoch_substitution_rejected",
        replace(
            evidence.grant,
            security_epoch=evidence.grant.security_epoch + 1,
        ),
    )
    reject_grant_substitution(
        "plan_grant_revocation_epoch_substitution_rejected",
        replace(
            evidence.grant,
            revocation_epoch=evidence.grant.revocation_epoch + 1,
        ),
    )
    reject_grant_substitution(
        "plan_grant_challenge_substitution_rejected",
        replace(
            evidence.grant,
            operation_challenge=_uuid_for(("forged-challenge",)),
        ),
    )
    reject_grant_substitution(
        "plan_grant_scope_substitution_rejected",
        replace(
            evidence.grant,
            exact_scope_digests=(hashlib.sha256(b"forged-scope").hexdigest(),),
        ),
    )
    reject_grant_substitution(
        "plan_grant_boundary_inventory_substitution_rejected",
        replace(
            evidence.grant,
            exact_boundary_member_identities=tuple(
                reversed(evidence.grant.exact_boundary_member_identities)
            ),
        ),
    )

    def activate_with(
        *,
        preparation_mutator: Callable[
            [
                tuple[
                    tuple[AtomicAuthorityStore, BoundaryPreparationResult],
                    ...,
                ]
            ],
            tuple[
                tuple[AtomicAuthorityStore, BoundaryPreparationResult],
                ...,
            ],
        ] = lambda value: value,
        capability_mutator: Callable[
            [ObserverReadCapabilityEvidence],
            ObserverReadCapabilityEvidence,
        ] = lambda value: value,
    ) -> None:
        server, prepared, capability = _prepared_fixture_from_evidence(evidence)
        server.activate(
            evidence.plan.stable_registry_key,
            prepared_boundaries=preparation_mutator(prepared),
            predecessor_closure_receipt_digest=None,
            capability_evidence=capability_mutator(capability),
            commit_time=110,
        )

    _expect_rejection(
        "forged_prepared_member_receipt_rejected",
        lambda: activate_with(
            preparation_mutator=lambda prepared: (
                (
                    prepared[0][0],
                    replace(
                        prepared[0][1],
                        enforcement_receipt=replace(
                            prepared[0][1].enforcement_receipt,
                            canonical_grant_digest=hashlib.sha256(
                                b"forged-grant"
                            ).hexdigest(),
                        ),
                    ),
                ),
                *prepared[1:],
            )
        ),
        accepted,
    )
    _expect_rejection(
        "incomplete_prepared_member_set_rejected",
        lambda: activate_with(preparation_mutator=lambda prepared: prepared[:-1]),
        accepted,
    )
    _expect_rejection(
        "writable_observer_capability_operation_rejected",
        lambda: activate_with(
            capability_mutator=lambda capability: replace(
                capability,
                capability=replace(
                    capability.capability,
                    operations=(*OBSERVER_READ_OPERATIONS, "put"),
                ),
            )
        ),
        accepted,
    )
    _expect_rejection(
        "wrong_session_observer_capability_rejected",
        lambda: activate_with(
            capability_mutator=lambda capability: replace(
                capability,
                capability=replace(
                    capability.capability,
                    manifest_session_scope=(
                        capability.capability.manifest_session_scope[0],
                        _uuid_for(("wrong-capability-generation",)),
                    ),
                ),
            )
        ),
        accepted,
    )
    _expect_rejection(
        "wrong_requester_observer_capability_rejected",
        lambda: activate_with(
            capability_mutator=lambda capability: replace(
                capability,
                capability=replace(
                    capability.capability,
                    observer_principal="forged-observer",
                ),
            )
        ),
        accepted,
    )
    capability_evidence = evidence.capability_evidence
    manifest = evidence.default_deny_manifest
    authorized_subscribe_member = next(
        member
        for member in evidence.plan.boundary_members
        if member.read_scope.operation == "subscribe"
    )
    widened_context = replace(
        capability_evidence.verified_transport_context,
        not_after=evidence.plan.server_grant_not_after + 1,
    )
    widened_capability_evidence = ObserverReadCapabilityIssuer().issue(
        manifest=manifest,
        context=widened_context,
        trusted_time=100,
    )
    _expect_rejection(
        "capability_wider_than_server_grant_deadline_rejected",
        lambda: activate_with(
            capability_mutator=lambda _capability: widened_capability_evidence
        ),
        accepted,
    )

    def validate_capability_with(
        candidate: ObserverReadCapabilityEvidence,
        *,
        candidate_manifest: ObserverDefaultDenyManifest = manifest,
        trusted_time: int = 110,
    ) -> None:
        _validate_capability_evidence(
            candidate,
            manifest=candidate_manifest,
            trusted_time=trusted_time,
        )

    capability_hostiles: tuple[tuple[str, ObserverReadCapabilityEvidence, int], ...] = (
        (
            "forged_capability_identifier_rejected",
            replace(
                capability_evidence,
                capability=replace(
                    capability_evidence.capability,
                    capability_id=_uuid_for(("forged-capability",)),
                ),
            ),
            110,
        ),
        (
            "forged_capability_seal_tag_rejected",
            replace(
                capability_evidence,
                seal=replace(
                    capability_evidence.seal,
                    authentication_tag="0" * 64,
                ),
            ),
            110,
        ),
        (
            "capability_missing_issuer_retention_rejected",
            replace(
                capability_evidence,
                issuer_snapshot=replace(
                    capability_evidence.issuer_snapshot,
                    retained_issuances=(),
                ),
            ),
            110,
        ),
        (
            "capability_issuer_snapshot_rollback_rejected",
            replace(
                capability_evidence,
                issuer_snapshot=replace(
                    capability_evidence.issuer_snapshot,
                    snapshot_version=0,
                ),
            ),
            110,
        ),
        (
            "capability_cross_issuer_key_rejected",
            replace(
                capability_evidence,
                seal=replace(
                    capability_evidence.seal,
                    issuer_key_id="forged-capability-issuer:key:1",
                ),
            ),
            110,
        ),
        (
            "capability_cross_principal_copy_rejected",
            replace(
                capability_evidence,
                verified_transport_context=replace(
                    capability_evidence.verified_transport_context,
                    authenticated_principal="observer-b",
                ),
            ),
            110,
        ),
        (
            "capability_cross_connection_copy_rejected",
            replace(
                capability_evidence,
                verified_transport_context=replace(
                    capability_evidence.verified_transport_context,
                    connection_instance="tls-connection-observer-a-2",
                ),
            ),
            110,
        ),
        (
            "capability_cross_replay_domain_copy_rejected",
            replace(
                capability_evidence,
                verified_transport_context=replace(
                    capability_evidence.verified_transport_context,
                    replay_domain="observer-ingress-replay-domain-b",
                ),
            ),
            110,
        ),
        (
            "capability_cross_session_copy_rejected",
            replace(
                capability_evidence,
                verified_transport_context=replace(
                    capability_evidence.verified_transport_context,
                    session_generation=_uuid_for(("cross-session-capability",)),
                ),
            ),
            110,
        ),
        (
            "capability_cross_realm_copy_rejected",
            replace(
                capability_evidence,
                verified_transport_context=replace(
                    capability_evidence.verified_transport_context,
                    authority_realm_key=("body-service", "other-realm"),
                ),
            ),
            110,
        ),
        (
            "capability_cross_security_state_copy_rejected",
            replace(
                capability_evidence,
                verified_transport_context=replace(
                    capability_evidence.verified_transport_context,
                    security_state_digest=SECURITY_STATE_DIGEST_2,
                ),
            ),
            110,
        ),
        (
            "capability_cross_security_epoch_copy_rejected",
            replace(
                capability_evidence,
                verified_transport_context=replace(
                    capability_evidence.verified_transport_context,
                    security_epoch=8,
                ),
            ),
            110,
        ),
        (
            "capability_cross_revocation_epoch_copy_rejected",
            replace(
                capability_evidence,
                verified_transport_context=replace(
                    capability_evidence.verified_transport_context,
                    revocation_epoch=12,
                ),
            ),
            110,
        ),
        (
            "capability_cross_manifest_copy_rejected",
            replace(
                capability_evidence,
                verified_transport_context=replace(
                    capability_evidence.verified_transport_context,
                    default_deny_manifest_digest=hashlib.sha256(
                        b"other-manifest"
                    ).hexdigest(),
                ),
            ),
            110,
        ),
        (
            "capability_scope_widening_rejected",
            replace(
                capability_evidence,
                capability=replace(
                    capability_evidence.capability,
                    exact_scope_digests=(
                        *capability_evidence.capability.exact_scope_digests,
                        hashlib.sha256(b"forged-scope").hexdigest(),
                    ),
                ),
            ),
            110,
        ),
        (
            "capability_not_after_equality_rejected",
            capability_evidence,
            capability_evidence.capability.not_after,
        ),
        (
            "capability_future_use_rejected",
            replace(
                capability_evidence,
                capability=replace(
                    capability_evidence.capability,
                    issued_at=111,
                ),
            ),
            110,
        ),
    )
    for label, candidate, trusted_time in capability_hostiles:
        _expect_rejection(
            label,
            lambda candidate=candidate, trusted_time=trusted_time: (
                validate_capability_with(candidate, trusted_time=trusted_time)
            ),
            accepted,
        )

    zero_security_manifest = replace(
        manifest,
        entries=(
            replace(
                manifest.entries[0],
                security_state_digest="0" * 64,
            ),
        ),
    )
    zero_security_context = replace(
        capability_evidence.verified_transport_context,
        default_deny_manifest_digest=_digest(zero_security_manifest),
        security_state_digest="0" * 64,
    )
    _expect_rejection(
        "manifest_zero_security_state_rejected",
        lambda: _validate_default_deny_manifest(zero_security_manifest),
        accepted,
    )
    _expect_rejection(
        "capability_issuance_zero_security_state_rejected",
        lambda: ObserverReadCapabilityIssuer().issue(
            manifest=zero_security_manifest,
            context=zero_security_context,
            trusted_time=110,
        ),
        accepted,
    )
    _expect_rejection(
        "capability_issuance_zero_transport_evidence_rejected",
        lambda: ObserverReadCapabilityIssuer().issue(
            manifest=manifest,
            context=replace(
                capability_evidence.verified_transport_context,
                transport_verification_evidence_digest="0" * 64,
            ),
            trusted_time=110,
        ),
        accepted,
    )

    manifest_hostiles = (
        (
            "manifest_allow_default_rejected",
            replace(manifest, default_decision="ALLOW"),
        ),
        (
            "manifest_wildcard_enable_rejected",
            replace(manifest, wildcard_entries_allowed=True),
        ),
        (
            "manifest_empty_default_deny_rejected",
            replace(manifest, entries=()),
        ),
        (
            "manifest_wildcard_principal_rejected",
            replace(
                manifest,
                entries=(replace(manifest.entries[0], authenticated_principal="*"),),
            ),
        ),
        (
            "manifest_write_operation_rejected",
            replace(
                manifest,
                entries=(
                    replace(
                        manifest.entries[0],
                        operations=(*OBSERVER_READ_OPERATIONS, "publish"),
                    ),
                ),
            ),
        ),
        (
            "manifest_literal_route_substitution_rejected",
            replace(
                manifest,
                entries=(
                    replace(
                        manifest.entries[0],
                        read_scopes=(
                            replace(
                                manifest.entries[0].read_scopes[0],
                                literal_route="synthetic-realm/session/other/observation",
                            ),
                            *manifest.entries[0].read_scopes[1:],
                        ),
                    ),
                ),
            ),
        ),
        (
            "capability_different_manifest_rejected",
            replace(manifest, manifest_id="observer-default-deny-manifest-v2"),
        ),
    )
    for label, hostile_manifest in manifest_hostiles:
        _expect_rejection(
            label,
            lambda hostile_manifest=hostile_manifest: validate_capability_with(
                capability_evidence,
                candidate_manifest=hostile_manifest,
            ),
            accepted,
        )

    def authorize_with(
        *,
        candidate: ObserverReadCapabilityEvidence = capability_evidence,
        live_context: VerifiedObserverTransportPrincipal = (
            capability_evidence.verified_transport_context
        ),
        operation: str | None = None,
        read_scope: CanonicalObserverReadScope = (
            authorized_subscribe_member.read_scope
        ),
        membership: ObserverBoundaryReadScopeMembership = (
            authorized_subscribe_member.scope_membership
        ),
        expected_boundary_identity: tuple[str, str, str] = (
            authorized_subscribe_member.boundary_principal,
            authorized_subscribe_member.boundary_instance,
            authorized_subscribe_member.deadline_policy_id,
        ),
        observer_instance: str = OBSERVER_INSTANCE,
        caller_operation_id: str = _uuid_for(("hostile-read", "default")),
        trusted_time: int = 111,
    ) -> None:
        recovered_server = ObserverAuthorizationServer()
        recovered_server.store = (
            AtomicAuthorityStore._from_validated_counterfactual_snapshot_for_test(
                evidence.server_snapshot,
                trusted_clock_sample=(
                    _fixture_continuous_recovery_clock_sample(evidence.server_snapshot)
                ),
            )
        )
        candidate_scope = (
            read_scope
            if operation is None
            else replace(read_scope, operation=operation)
        )
        recovered_server.authorize_read(
            candidate,
            live_transport_context=live_context,
            read_scope=candidate_scope,
            boundary_membership=membership,
            expected_boundary_identity=expected_boundary_identity,
            observer_instance=observer_instance,
            caller_operation_id=caller_operation_id,
            trusted_time=trusted_time,
        )

    _expect_rejection(
        "read_capability_publish_surface_rejected",
        lambda: authorize_with(operation="publish"),
        accepted,
    )
    _expect_rejection(
        "read_capability_unknown_surface_rejected",
        lambda: authorize_with(operation="unknown-read"),
        accepted,
    )
    _expect_rejection(
        "read_capability_ungranted_scope_rejected",
        lambda: authorize_with(
            read_scope=replace(
                authorized_subscribe_member.read_scope,
                scope_digest=hashlib.sha256(b"ungranted-scope").hexdigest(),
            )
        ),
        accepted,
    )
    _expect_rejection(
        "read_capability_cross_live_principal_rejected",
        lambda: authorize_with(
            live_context=replace(
                capability_evidence.verified_transport_context,
                authenticated_principal="observer-b",
            )
        ),
        accepted,
    )
    history_member = next(
        member
        for member in evidence.plan.boundary_members
        if member.read_scope.operation == "history_query"
    )
    _expect_rejection(
        "read_capability_cross_operation_scope_rejected",
        lambda: authorize_with(
            operation="subscribe",
            read_scope=history_member.read_scope,
            membership=history_member.scope_membership,
        ),
        accepted,
    )
    _expect_rejection(
        "read_capability_cross_live_connection_rejected",
        lambda: authorize_with(
            live_context=replace(
                capability_evidence.verified_transport_context,
                connection_instance="tls-connection-observer-a-2",
            )
        ),
        accepted,
    )

    def collide_distinct_same_tick_operations() -> None:
        recovered_server = ObserverAuthorizationServer()
        recovered_server.store = (
            AtomicAuthorityStore._from_validated_counterfactual_snapshot_for_test(
                evidence.server_snapshot,
                trusted_clock_sample=(
                    _fixture_continuous_recovery_clock_sample(evidence.server_snapshot)
                ),
            )
        )
        first = recovered_server.authorize_read(
            capability_evidence,
            live_transport_context=(capability_evidence.verified_transport_context),
            read_scope=authorized_subscribe_member.read_scope,
            boundary_membership=authorized_subscribe_member.scope_membership,
            expected_boundary_identity=(
                authorized_subscribe_member.boundary_principal,
                authorized_subscribe_member.boundary_instance,
                authorized_subscribe_member.deadline_policy_id,
            ),
            observer_instance=OBSERVER_INSTANCE,
            caller_operation_id=_uuid_for(("same-tick-distinct-read", 1)),
            trusted_time=111,
        )
        second = recovered_server.authorize_read(
            capability_evidence,
            live_transport_context=(capability_evidence.verified_transport_context),
            read_scope=authorized_subscribe_member.read_scope,
            boundary_membership=authorized_subscribe_member.scope_membership,
            expected_boundary_identity=(
                authorized_subscribe_member.boundary_principal,
                authorized_subscribe_member.boundary_instance,
                authorized_subscribe_member.deadline_policy_id,
            ),
            observer_instance=OBSERVER_INSTANCE,
            caller_operation_id=_uuid_for(("same-tick-distinct-read", 2)),
            trusted_time=111,
        )
        _require(
            first.decision_id == second.decision_id
            or first.semantic_decision_digest == second.semantic_decision_digest,
            "distinct same-tick caller operations retain distinct decision "
            "identities and semantic artifacts",
        )

    _expect_rejection(
        "distinct_same_tick_read_operation_collision_rejected",
        collide_distinct_same_tick_operations,
        accepted,
    )

    def reuse_operation_id_for_altered_scope() -> None:
        recovered_server = ObserverAuthorizationServer()
        recovered_server.store = (
            AtomicAuthorityStore._from_validated_counterfactual_snapshot_for_test(
                evidence.server_snapshot,
                trusted_clock_sample=(
                    _fixture_continuous_recovery_clock_sample(evidence.server_snapshot)
                ),
            )
        )
        reused_operation_id = _uuid_for(("same-read-id-altered-scope",))
        recovered_server.authorize_read(
            capability_evidence,
            live_transport_context=(capability_evidence.verified_transport_context),
            read_scope=authorized_subscribe_member.read_scope,
            boundary_membership=authorized_subscribe_member.scope_membership,
            expected_boundary_identity=(
                authorized_subscribe_member.boundary_principal,
                authorized_subscribe_member.boundary_instance,
                authorized_subscribe_member.deadline_policy_id,
            ),
            observer_instance=OBSERVER_INSTANCE,
            caller_operation_id=reused_operation_id,
            trusted_time=111,
        )
        recovered_server.authorize_read(
            capability_evidence,
            live_transport_context=(capability_evidence.verified_transport_context),
            read_scope=history_member.read_scope,
            boundary_membership=history_member.scope_membership,
            expected_boundary_identity=(
                history_member.boundary_principal,
                history_member.boundary_instance,
                history_member.deadline_policy_id,
            ),
            observer_instance=OBSERVER_INSTANCE,
            caller_operation_id=reused_operation_id,
            trusted_time=111,
        )

    _expect_rejection(
        "same_read_operation_id_altered_scope_rejected",
        reuse_operation_id_for_altered_scope,
        accepted,
    )

    def authorize_after_revocation() -> None:
        recovered_server = ObserverAuthorizationServer()
        recovered_server.store = (
            AtomicAuthorityStore._from_validated_counterfactual_snapshot_for_test(
                evidence.server_snapshot,
                trusted_clock_sample=(
                    _fixture_continuous_recovery_clock_sample(evidence.server_snapshot)
                ),
            )
        )
        recovered_server.terminate(
            evidence.plan.stable_registry_key,
            terminal_reason="REVOKED",
            actor_or_event="security-authority-revocation",
            policy_rule_digest=hashlib.sha256(b"revocation-policy").hexdigest(),
            policy_inputs_digest=hashlib.sha256(b"revocation-inputs").hexdigest(),
            authority_source_receipt_digest=hashlib.sha256(
                b"revocation-source-receipt"
            ).hexdigest(),
            commit_time=112,
        )
        recovered_server.authorize_read(
            capability_evidence,
            live_transport_context=capability_evidence.verified_transport_context,
            read_scope=authorized_subscribe_member.read_scope,
            boundary_membership=authorized_subscribe_member.scope_membership,
            expected_boundary_identity=(
                authorized_subscribe_member.boundary_principal,
                authorized_subscribe_member.boundary_instance,
                authorized_subscribe_member.deadline_policy_id,
            ),
            observer_instance=OBSERVER_INSTANCE,
            caller_operation_id=_uuid_for(("hostile-read", "after-terminal")),
            trusted_time=113,
        )

    _expect_rejection(
        "read_capability_after_revocation_terminal_rejected",
        authorize_after_revocation,
        accepted,
    )

    deadline_intent = _intent(
        AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE,
        "SERVER_GRANT_NOT_AFTER",
        SERVER_CLOCK_1,
        10,
        store_id="observer-authorization-server",
        authority_principal=SERVER_PRINCIPAL,
        transition_kind="ACTIVATE_PENDING_GRANT",
        operation_id=_uuid_for(("hostile-deadline-equality",)),
        expected_prior_state_digest=None,
        expected_prior_selector_version=0,
        security_state_digest=SECURITY_STATE_DIGEST,
    )
    _expect_rejection(
        "authorization_deadline_equality_rejected",
        lambda: _evaluate_intents(
            (deadline_intent,),
            commit_time=10,
            installed_successor_digest=hashlib.sha256(b"successor").hexdigest(),
            installed_selector_version=1,
        ),
        accepted,
    )
    expiry_intent = _intent(
        EXPIRY_AT_OR_AFTER_EXCLUSIVE_DEADLINE,
        "SERVER_GRANT_NOT_AFTER",
        SERVER_CLOCK_1,
        10,
        store_id="observer-authorization-server",
        authority_principal=SERVER_PRINCIPAL,
        transition_kind="TERMINATE_GRANT",
        operation_id=_uuid_for(("hostile-expiry-before-deadline",)),
        expected_prior_state_digest=None,
        expected_prior_selector_version=0,
        security_state_digest=SECURITY_STATE_DIGEST,
    )
    _expect_rejection(
        "expiry_before_deadline_rejected",
        lambda: _evaluate_intents(
            (expiry_intent,),
            commit_time=9,
            installed_successor_digest=hashlib.sha256(b"terminal").hexdigest(),
            installed_selector_version=1,
        ),
        accepted,
    )
    _expect_rejection(
        "unqualified_completion_margin_rejected",
        lambda: _intent(
            AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE,
            "SERVER_GRANT_NOT_AFTER",
            SERVER_CLOCK_1,
            10,
            store_id="observer-authorization-server",
            authority_principal=SERVER_PRINCIPAL,
            transition_kind="ACTIVATE_PENDING_GRANT",
            operation_id=_uuid_for(("hostile-qualified-margin",)),
            expected_prior_state_digest=None,
            expected_prior_selector_version=0,
            security_state_digest=SECURITY_STATE_DIGEST,
            margin=1,
        ),
        accepted,
    )

    server_snapshot = evidence.server_snapshot
    first_transition = server_snapshot.transitions[0]
    generic = _tuple_map(server_snapshot.objects)[
        first_transition.generic_commit_digest
    ]
    exact_signed = _tuple_map(server_snapshot.signed_bytes)[
        first_transition.generic_commit_digest
    ]
    _expect_rejection(
        "signed_wrong_principal_rejected",
        lambda: _verify_signed_bytes(
            generic,
            exact_signed,
            expected_principal="forged-principal",
            expected_key_id=first_transition.signing_key_id,
            expected_security_state=first_transition.security_state_digest,
        ),
        accepted,
    )
    _expect_rejection(
        "signed_wrong_key_rejected",
        lambda: _verify_signed_bytes(
            generic,
            exact_signed,
            expected_principal=first_transition.authority_principal,
            expected_key_id="forged-key",
            expected_security_state=first_transition.security_state_digest,
        ),
        accepted,
    )
    _expect_rejection(
        "signed_wrong_security_state_rejected",
        lambda: _verify_signed_bytes(
            generic,
            exact_signed,
            expected_principal=first_transition.authority_principal,
            expected_key_id=first_transition.signing_key_id,
            expected_security_state=SECURITY_STATE_DIGEST_2,
        ),
        accepted,
    )
    _expect_rejection(
        "signed_noncanonical_bytes_rejected",
        lambda: _verify_signed_bytes(
            generic,
            exact_signed + b" ",
            expected_principal=first_transition.authority_principal,
            expected_key_id=first_transition.signing_key_id,
            expected_security_state=first_transition.security_state_digest,
        ),
        accepted,
    )

    _expect_rejection(
        "recovery_version_drift_rejected",
        lambda: _validate_atomic_snapshot(
            replace(
                server_snapshot,
                snapshot_version=server_snapshot.snapshot_version + 1,
            )
        ),
        accepted,
    )
    _expect_rejection(
        "recovery_state_digest_drift_rejected",
        lambda: _validate_atomic_snapshot(
            replace(
                server_snapshot,
                state_digest=hashlib.sha256(b"forged-state").hexdigest(),
            )
        ),
        accepted,
    )
    _expect_rejection(
        "recovery_missing_signed_bytes_rejected",
        lambda: _validate_atomic_snapshot(
            replace(
                server_snapshot,
                signed_bytes=server_snapshot.signed_bytes[:-1],
            )
        ),
        accepted,
    )
    issuer_snapshot_digest = _digest(evidence.capability_evidence.issuer_snapshot)
    missing_issuer_objects = _tuple_map(server_snapshot.objects)
    missing_issuer_content = _tuple_map(server_snapshot.content_bytes)
    missing_issuer_objects.pop(issuer_snapshot_digest)
    missing_issuer_content.pop(issuer_snapshot_digest)
    _expect_rejection(
        "recovery_missing_capability_issuer_snapshot_rejected",
        lambda: _validate_atomic_snapshot(
            replace(
                server_snapshot,
                objects=tuple(sorted(missing_issuer_objects.items())),
                content_bytes=tuple(sorted(missing_issuer_content.items())),
            )
        ),
        accepted,
    )
    _expect_rejection(
        "recovery_key_drift_rejected",
        lambda: _validate_atomic_snapshot(
            replace(server_snapshot, authority_key_id="forged-key")
        ),
        accepted,
    )
    _expect_rejection(
        "recovery_security_drift_rejected",
        lambda: _validate_atomic_snapshot(
            replace(
                server_snapshot,
                security_state_digest=SECURITY_STATE_DIGEST_2,
            )
        ),
        accepted,
    )
    _expect_rejection(
        "recovery_clock_drift_rejected",
        lambda: _validate_atomic_snapshot(
            replace(server_snapshot, clock_incarnation=SERVER_CLOCK_2)
        ),
        accepted,
    )
    schema_drift_record = replace(
        server_snapshot.transitions[-1],
        required_specialized_receipt_types=(),
    )
    _expect_rejection(
        "recovery_receipt_schema_drift_rejected",
        lambda: _validate_atomic_snapshot(
            _snapshot_with_transition(
                server_snapshot,
                len(server_snapshot.transitions) - 1,
                schema_drift_record,
            )
        ),
        accepted,
    )
    unknown_kind_record = replace(
        server_snapshot.transitions[-1],
        transition_kind="UNKNOWN_UNALLOCATED_MUTATION",
    )
    _expect_rejection(
        "recovery_unknown_transition_kind_rejected",
        lambda: _validate_atomic_snapshot(
            _snapshot_with_transition(
                server_snapshot,
                len(server_snapshot.transitions) - 1,
                unknown_kind_record,
            )
        ),
        accepted,
    )

    boundary_snapshot = evidence.boundary_snapshots[0]
    release_transition_index = next(
        index
        for index, transition in enumerate(boundary_snapshot.transitions)
        if transition.transition_kind == "COMMIT_TRUSTED_DELIVERY_RELEASE_OUTBOX"
    )
    release_transition = boundary_snapshot.transitions[release_transition_index]
    co_schema_drift = replace(
        release_transition,
        required_co_committed_object_types=(),
    )
    _expect_rejection(
        "recovery_outbox_schema_drift_rejected",
        lambda: _validate_atomic_snapshot(
            _snapshot_with_transition(
                boundary_snapshot,
                release_transition_index,
                co_schema_drift,
            )
        ),
        accepted,
    )
    missing_outbox_objects = _tuple_map(boundary_snapshot.objects)
    missing_outbox_content = _tuple_map(boundary_snapshot.content_bytes)
    for digest in release_transition.co_committed_object_digests:
        missing_outbox_objects.pop(digest)
        missing_outbox_content.pop(digest)
    _expect_rejection(
        "recovery_missing_complete_outbox_rejected",
        lambda: _validate_atomic_snapshot(
            replace(
                boundary_snapshot,
                objects=tuple(sorted(missing_outbox_objects.items())),
                content_bytes=tuple(sorted(missing_outbox_content.items())),
            )
        ),
        accepted,
    )

    forged_outbox = replace(
        evidence.release.outbox_item,
        complete_payload=b"forged payload",
    )
    boundary = TrustedDeliveryBoundary(evidence.plan.boundary_members[0])
    boundary.store = (
        AtomicAuthorityStore._from_validated_counterfactual_snapshot_for_test(
            boundary_snapshot,
            trusted_clock_sample=(
                _fixture_continuous_recovery_clock_sample(boundary_snapshot)
            ),
        )
    )
    release_reservation = evidence.release.reservation
    release_member = evidence.plan.boundary_members[0]
    release_security_state = (
        release_member.security_state_digest,
        release_reservation.release_recipient_context.local_security_epoch,
        release_reservation.release_recipient_context.local_revocation_epoch,
    )
    release_observer_identity = (
        release_reservation.requester_principal,
        release_reservation.release_recipient_context.recipient_instance,
    )
    release_boundary_identity = (
        release_member.boundary_principal,
        release_member.boundary_instance,
        release_member.deadline_policy_id,
    )

    def validate_release_cas_variant(
        *,
        decision: SealedObserverReadAuthorizationDecision = (
            evidence.read_authorization_decision
        ),
        release_context: SyntheticVerifiedReleaseRecipientContext = (
            release_reservation.release_recipient_context
        ),
        mapping: QualifiedDecisionDeadlineMapping = (
            release_reservation.qualified_deadline_mapping
        ),
        currentness: SyntheticAuthenticatedGrantCurrentnessEvidence = (
            release_reservation.grant_currentness_evidence
        ),
        cas: ObserverReadReleaseCAS = release_reservation.release_cas,
        expected_release_context_digest: str = (
            release_recipient_artifact_digest(
                release_reservation.release_recipient_context
            )
        ),
    ) -> None:
        try:
            validate_release_cas(
                cas,
                scope=release_member.read_scope,
                membership=release_member.scope_membership,
                decision=decision,
                release_context=release_context,
                qualified_deadline_mapping=mapping,
                grant_currentness_evidence=currentness,
                expected_observer_identity=release_observer_identity,
                expected_boundary_identity=release_boundary_identity,
                expected_authorization_audience=(
                    release_member.read_scope.authorization_audience
                ),
                expected_authorization_cut=(evidence.retained_read_authorization_cut),
                expected_issuer_identity=(
                    SERVER_PRINCIPAL,
                    SERVER_KEY_ID,
                    SERVER_STATE_INCARNATION,
                ),
                expected_release_recipient_identity=(release_observer_identity),
                expected_release_transport_context=(
                    release_reservation.expected_release_transport_context
                ),
                expected_local_security_state=release_security_state,
                expected_release_context_artifact_digest=(
                    expected_release_context_digest
                ),
                expected_grant_currentness_state_cut=(
                    release_reservation.expected_grant_currentness_state_cut
                ),
                expected_deadline_mapping_state_cut=(
                    release_reservation.expected_deadline_mapping_state_cut
                ),
                release_idempotency_key=(
                    release_reservation.release_cas.release_idempotency_key
                ),
                expected_boundary_clock_incarnation=(
                    release_member.clock_mapping.boundary_clock_incarnation
                ),
                expected_mapping_policy_artifact_digest=_digest(
                    release_member.clock_mapping
                ),
                checked_at=(release_reservation.grant_currentness_evidence.verified_at),
                fixture_key=_READ_DECISION_SEAL_KEY,
            )
        except BridgeValidationError as exc:
            raise ProbeError("hostile release CAS variant rejected") from exc

    def validate_committed_outbox_variant(
        artifact: SyntheticCommittedObserverReadOutboxArtifact = (
            evidence.release.outbox_item.committed_bridge_outbox_artifact
        ),
        *,
        commit_receipt: SyntheticObserverReadOutboxCommitReceipt = (
            evidence.release.outbox_item.bridge_commit_receipt
        ),
        commit_state_cut: ExpectedCommittedObserverReadOutboxStateCut = (
            evidence.release.outbox_item.expected_bridge_commit_state_cut
        ),
        exact_payload: bytes = evidence.release.outbox_item.complete_payload,
        expected_stable_outbox_item_id: str = (
            evidence.release.outbox_item.stable_item_id
        ),
        expected_transport_idempotency_key: str = (
            evidence.release.outbox_item.idempotency_key
        ),
        expected_artifact_digest: str = (
            committed_outbox_artifact_digest(
                evidence.release.outbox_item.committed_bridge_outbox_artifact
            )
        ),
    ) -> None:
        try:
            validate_committed_outbox_artifact(
                artifact,
                scope=release_member.read_scope,
                membership=release_member.scope_membership,
                release_cas=release_reservation.release_cas,
                validated_release_cas_receipt=(
                    release_reservation.validated_release_cas_receipt
                ),
                commit_receipt=commit_receipt,
                expected_commit_state_cut=commit_state_cut,
                release_context=release_reservation.release_recipient_context,
                expected_boundary_identity=release_boundary_identity,
                expected_recipient_identity=release_observer_identity,
                expected_boundary_clock_incarnation=(
                    release_member.clock_mapping.boundary_clock_incarnation
                ),
                expected_stable_outbox_item_id=expected_stable_outbox_item_id,
                expected_exact_payload=exact_payload,
                expected_transport_idempotency_key=(expected_transport_idempotency_key),
                expected_artifact_digest=expected_artifact_digest,
                checked_at=(
                    evidence.release.outbox_item.committed_bridge_outbox_artifact.committed_at
                ),
                fixture_key=_READ_DECISION_SEAL_KEY,
            )
        except BridgeValidationError as exc:
            raise ProbeError("hostile committed outbox variant rejected") from exc

    def validate_dispatch_variant(
        context: SyntheticAuthenticatedDispatchContext,
        *,
        exact_payload: bytes = evidence.release.outbox_item.complete_payload,
        expected_context_artifact_digest: str = (
            evidence.drain_fact.dispatch_context_artifact_digest
        ),
    ) -> None:
        try:
            validate_dispatch_context(
                context,
                scope=release_member.read_scope,
                membership=release_member.scope_membership,
                release_context=release_reservation.release_recipient_context,
                release_cas=release_reservation.release_cas,
                validated_release_cas_receipt=(
                    release_reservation.validated_release_cas_receipt
                ),
                committed_outbox=(
                    evidence.release.outbox_item.committed_bridge_outbox_artifact
                ),
                commit_receipt=(evidence.release.outbox_item.bridge_commit_receipt),
                expected_commit_state_cut=(
                    evidence.release.outbox_item.expected_bridge_commit_state_cut
                ),
                expected_boundary_identity=release_boundary_identity,
                expected_recipient_identity=release_observer_identity,
                expected_release_transport_context=(
                    release_reservation.expected_release_transport_context
                ),
                expected_release_security_state=release_security_state,
                expected_boundary_clock_incarnation=(
                    release_member.clock_mapping.boundary_clock_incarnation
                ),
                expected_release_context_artifact_digest=(
                    release_recipient_artifact_digest(
                        release_reservation.release_recipient_context
                    )
                ),
                release_context_checked_at=(
                    release_reservation.release_recipient_context.verified_at
                ),
                expected_stable_outbox_item_id=(
                    evidence.release.outbox_item.stable_item_id
                ),
                actual_dispatch_payload=exact_payload,
                expected_committed_outbox_artifact_digest=(
                    committed_outbox_artifact_digest(
                        evidence.release.outbox_item.committed_bridge_outbox_artifact
                    )
                ),
                expected_dispatch_attempt_id=(evidence.drain_fact.attempt_identity),
                expected_transport_idempotency_key=(
                    evidence.release.outbox_item.idempotency_key
                ),
                expected_local_security_state=release_security_state,
                expected_destination_cut=(
                    evidence.drain_fact.expected_dispatch_destination_cut
                ),
                expected_dispatch_context_artifact_digest=(
                    expected_context_artifact_digest
                ),
                checked_at=evidence.drain_fact.dispatch_context.verified_at,
                fixture_key=_READ_DECISION_SEAL_KEY,
            )
        except BridgeValidationError as exc:
            raise ProbeError("hostile dispatch variant rejected") from exc

    restarted_ingress = seal_authorization_ingress_context(
        replace(
            evidence.read_authorization_decision.authorization_ingress_context,
            coordinator_clock_incarnation=SERVER_CLOCK_2,
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    restarted_ingress_decision = seal_read_decision(
        replace(
            evidence.read_authorization_decision,
            authorization_ingress_context=restarted_ingress,
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    rebound_ingress = seal_authorization_ingress_context(
        replace(
            evidence.read_authorization_decision.authorization_ingress_context,
            connection_instance="hostile-authorization-connection",
            replay_domain="hostile-authorization-replay-domain",
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    rebound_ingress_decision = seal_read_decision(
        replace(
            evidence.read_authorization_decision,
            authorization_ingress_context=rebound_ingress,
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    rebound_ingress_cut = replace(
        evidence.retained_read_authorization_cut,
        authorization_ingress_artifact_digest=(
            authorization_ingress_artifact_digest(rebound_ingress)
        ),
    )
    restarted_release_context = seal_release_recipient_context(
        replace(
            release_reservation.release_recipient_context,
            boundary_clock_incarnation=OBSERVER_CLOCK_2,
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    rebound_release_context = seal_release_recipient_context(
        replace(
            release_reservation.release_recipient_context,
            connection_instance="hostile-release-connection",
            replay_domain="hostile-release-replay-domain",
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    rebound_release_cas = seal_release_cas(
        replace(
            release_reservation.release_cas,
            release_recipient_context_artifact_digest=(
                release_recipient_artifact_digest(rebound_release_context)
            ),
        )
    )
    restarted_mapping = seal_qualified_deadline_mapping(
        replace(
            release_reservation.qualified_deadline_mapping,
            boundary_clock_incarnation=OBSERVER_CLOCK_2,
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    requalified_mapping = seal_qualified_deadline_mapping(
        replace(
            release_reservation.qualified_deadline_mapping,
            qualification_digest=hashlib.sha256(
                b"hostile-self-consistent-clock-qualification"
            ).hexdigest(),
            source_receipt_digest=hashlib.sha256(
                b"hostile-self-consistent-clock-source-receipt"
            ).hexdigest(),
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    requalified_mapping_cas = seal_release_cas(
        replace(
            release_reservation.release_cas,
            qualified_deadline_mapping_artifact_digest=(
                qualified_deadline_mapping_artifact_digest(requalified_mapping)
            ),
        )
    )
    fabricated_currentness = seal_grant_currentness_evidence(
        replace(
            release_reservation.grant_currentness_evidence,
            boundary_state_head_digest=hashlib.sha256(
                b"fabricated-grant-currentness-state"
            ).hexdigest(),
            grant_currentness_receipt_digest=hashlib.sha256(
                b"fabricated-grant-currentness-receipt"
            ).hexdigest(),
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    reused_currentness = seal_grant_currentness_evidence(
        replace(
            release_reservation.grant_currentness_evidence,
            prior_release_count=1,
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    reused_cas = seal_release_cas(
        replace(
            release_reservation.release_cas,
            grant_currentness_evidence_artifact_digest=(
                grant_currentness_artifact_digest(reused_currentness)
            ),
            prior_release_count=1,
            release_ordinal=2,
            prior_release_counter_state_digest=(
                reused_currentness.release_counter_state_digest
            ),
            next_release_counter_state_digest=(
                next_grant_release_counter_state_digest(
                    evidence=reused_currentness,
                    release_idempotency_key=(
                        release_reservation.release_cas.release_idempotency_key
                    ),
                    release_ordinal=2,
                )
            ),
        )
    )
    overflow_cas = seal_release_cas(
        replace(
            release_reservation.release_cas,
            release_ordinal=2,
            next_release_counter_state_digest=(
                next_grant_release_counter_state_digest(
                    evidence=release_reservation.grant_currentness_evidence,
                    release_idempotency_key=(
                        release_reservation.release_cas.release_idempotency_key
                    ),
                    release_ordinal=2,
                )
            ),
        )
    )
    sibling_exact_payload = b"synthetic-valid-losing-sibling-payload"
    sibling_outbox = seal_committed_outbox_artifact(
        replace(
            evidence.release.outbox_item.committed_bridge_outbox_artifact,
            exact_payload=sibling_exact_payload,
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    sibling_commit_receipt = seal_outbox_commit_receipt(
        replace(
            evidence.release.outbox_item.bridge_commit_receipt,
            transaction_id=_uuid_for(("valid-same-quota-losing-outbox-sibling",)),
            committed_outbox_artifact_digest=(
                committed_outbox_artifact_digest(sibling_outbox)
            ),
            outbox_identity_digest=sibling_outbox.outbox_identity_digest,
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    sibling_commit_state_cut = ExpectedCommittedObserverReadOutboxStateCut(
        transaction_id=sibling_commit_receipt.transaction_id,
        prior_storage_state_head_digest=(
            sibling_commit_receipt.prior_storage_state_head_digest
        ),
        installed_storage_state_head_digest=(
            sibling_commit_receipt.installed_storage_state_head_digest
        ),
        validated_release_cas_receipt_artifact_digest=(
            sibling_commit_receipt.validated_release_cas_receipt_artifact_digest
        ),
        committed_outbox_artifact_digest=(
            committed_outbox_artifact_digest(sibling_outbox)
        ),
        commit_receipt_artifact_digest=(
            outbox_commit_receipt_artifact_digest(sibling_commit_receipt)
        ),
    )
    validate_committed_outbox_variant()
    validate_committed_outbox_variant(
        sibling_outbox,
        commit_receipt=sibling_commit_receipt,
        commit_state_cut=sibling_commit_state_cut,
        exact_payload=sibling_exact_payload,
        expected_artifact_digest=committed_outbox_artifact_digest(sibling_outbox),
    )
    _require(
        sibling_outbox.release_cas_artifact_digest
        == release_reservation.release_cas.cas_digest
        and sibling_outbox.installed_release_counter_state_digest
        == release_reservation.release_cas.next_release_counter_state_digest
        and sibling_commit_receipt.prior_storage_state_head_digest
        == (
            evidence.release.outbox_item.bridge_commit_receipt.prior_storage_state_head_digest
        )
        and sibling_commit_receipt.transaction_id
        != evidence.release.outbox_item.bridge_commit_receipt.transaction_id
        and sibling_outbox.outbox_identity_digest
        != (
            evidence.release.outbox_item.committed_bridge_outbox_artifact.outbox_identity_digest
        )
        and committed_outbox_artifact_digest(sibling_outbox)
        != committed_outbox_artifact_digest(
            evidence.release.outbox_item.committed_bridge_outbox_artifact
        )
        and sibling_commit_receipt.installed_storage_state_head_digest
        != (
            evidence.release.outbox_item.bridge_commit_receipt.installed_storage_state_head_digest
        ),
        "two individually valid same-CAS outbox siblings did not preserve the "
        "quota successor while separating transaction, payload, outbox, and "
        "installed-storage identity",
    )
    foreign_cas_outbox = seal_committed_outbox_artifact(
        replace(
            evidence.release.outbox_item.committed_bridge_outbox_artifact,
            release_cas_artifact_digest=hashlib.sha256(
                b"foreign-release-cas"
            ).hexdigest(),
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    payload_swapped_outbox = seal_committed_outbox_artifact(
        replace(
            evidence.release.outbox_item.committed_bridge_outbox_artifact,
            exact_payload=b"synthetic-hostile-payload-swap",
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    length_tampered_outbox = replace(
        evidence.release.outbox_item.committed_bridge_outbox_artifact,
        payload_octet_length=(evidence.release.outbox_item.payload_length + 1),
    )
    split_write_commit_receipt = seal_outbox_commit_receipt(
        replace(
            evidence.release.outbox_item.bridge_commit_receipt,
            prior_storage_state_head_digest=hashlib.sha256(
                b"hostile-split-write-prior-storage-head"
            ).hexdigest(),
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    forged_commit_receipt = seal_outbox_commit_receipt(
        replace(
            evidence.release.outbox_item.bridge_commit_receipt,
            committed_outbox_artifact_digest=hashlib.sha256(
                b"hostile-forged-committed-outbox-artifact"
            ).hexdigest(),
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    restarted_dispatch = seal_dispatch_context(
        replace(
            evidence.drain_fact.dispatch_context,
            boundary_clock_incarnation=OBSERVER_CLOCK_2,
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    altered_dispatch_attempt = seal_dispatch_context(
        replace(
            evidence.drain_fact.dispatch_context,
            dispatch_attempt_id=_uuid_for(("hostile-dispatch-attempt",)),
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    altered_dispatch_length = seal_dispatch_context(
        replace(
            evidence.drain_fact.dispatch_context,
            payload_octet_length=(
                evidence.drain_fact.dispatch_context.payload_octet_length + 1
            ),
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    rebound_dispatch_destination_cut = replace(
        evidence.drain_fact.expected_dispatch_destination_cut,
        connection_instance="hostile-dispatch-connection",
        replay_domain="hostile-dispatch-replay-domain",
        transport_gate_state_digest="0" * 64,
    )
    rebound_dispatch_destination_cut = replace(
        rebound_dispatch_destination_cut,
        transport_gate_state_digest=dispatch_transport_gate_state_digest(
            rebound_dispatch_destination_cut
        ),
    )
    rebound_dispatch = seal_dispatch_context(
        replace(
            evidence.drain_fact.dispatch_context,
            connection_instance=rebound_dispatch_destination_cut.connection_instance,
            replay_domain=rebound_dispatch_destination_cut.replay_domain,
            destination_cut_digest=dispatch_destination_cut_digest(
                rebound_dispatch_destination_cut
            ),
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )
    regated_dispatch_destination_cut = replace(
        evidence.drain_fact.expected_dispatch_destination_cut,
        transport_gate_state_digest="0" * 64,
        transport_gate_epoch=(
            evidence.drain_fact.expected_dispatch_destination_cut.transport_gate_epoch
            + 1
        ),
    )
    regated_dispatch_destination_cut = replace(
        regated_dispatch_destination_cut,
        transport_gate_state_digest=dispatch_transport_gate_state_digest(
            regated_dispatch_destination_cut
        ),
    )
    regated_dispatch = seal_dispatch_context(
        replace(
            evidence.drain_fact.dispatch_context,
            destination_cut_digest=dispatch_destination_cut_digest(
                regated_dispatch_destination_cut
            ),
            transport_gate_state_digest=(
                regated_dispatch_destination_cut.transport_gate_state_digest
            ),
            transport_gate_epoch=(
                regated_dispatch_destination_cut.transport_gate_epoch
            ),
        ),
        fixture_key=_READ_DECISION_SEAL_KEY,
    )

    def validate_restarted_ingress_decision() -> None:
        try:
            validate_read_decision(
                restarted_ingress_decision,
                scope=release_member.read_scope,
                membership=release_member.scope_membership,
                expected_boundary_identity=release_boundary_identity,
                expected_observer_identity=release_observer_identity,
                expected_authorization_audience=(
                    release_member.read_scope.authorization_audience
                ),
                expected_authorization_cut=(evidence.retained_read_authorization_cut),
                expected_issuer_identity=(
                    SERVER_PRINCIPAL,
                    SERVER_KEY_ID,
                    SERVER_STATE_INCARNATION,
                ),
                fixture_key=_READ_DECISION_SEAL_KEY,
            )
        except BridgeValidationError as exc:
            raise ProbeError("hostile ingress decision rejected") from exc

    def validate_rebound_ingress_decision() -> None:
        try:
            validate_read_decision(
                rebound_ingress_decision,
                scope=release_member.read_scope,
                membership=release_member.scope_membership,
                expected_boundary_identity=release_boundary_identity,
                expected_observer_identity=release_observer_identity,
                expected_authorization_audience=(
                    release_member.read_scope.authorization_audience
                ),
                expected_authorization_cut=rebound_ingress_cut,
                expected_issuer_identity=(
                    SERVER_PRINCIPAL,
                    SERVER_KEY_ID,
                    SERVER_STATE_INCARNATION,
                ),
                fixture_key=_READ_DECISION_SEAL_KEY,
            )
        except BridgeValidationError as exc:
            raise ProbeError("hostile rebound ingress decision rejected") from exc

    for label, action in (
        (
            "read_resealed_authorization_ingress_clock_restart_rejected",
            validate_restarted_ingress_decision,
        ),
        (
            "read_resealed_authorization_transport_rebinding_rejected",
            validate_rebound_ingress_decision,
        ),
        (
            "release_resealed_recipient_clock_restart_rejected",
            lambda: validate_release_cas_variant(
                release_context=restarted_release_context
            ),
        ),
        (
            "release_resealed_transport_rebinding_rejected",
            lambda: validate_release_cas_variant(
                release_context=rebound_release_context,
                cas=rebound_release_cas,
                expected_release_context_digest=(
                    release_recipient_artifact_digest(rebound_release_context)
                ),
            ),
        ),
        (
            "release_resealed_mapping_clock_restart_rejected",
            lambda: validate_release_cas_variant(mapping=restarted_mapping),
        ),
        (
            "release_resealed_mapping_receipt_substitution_rejected",
            lambda: validate_release_cas_variant(
                mapping=requalified_mapping,
                cas=requalified_mapping_cas,
            ),
        ),
        (
            "release_resealed_fabricated_currentness_rejected",
            lambda: validate_release_cas_variant(currentness=fabricated_currentness),
        ),
        (
            "release_resealed_quota_reuse_rejected",
            lambda: validate_release_cas_variant(
                currentness=reused_currentness,
                cas=reused_cas,
            ),
        ),
        (
            "release_resealed_quota_overflow_rejected",
            lambda: validate_release_cas_variant(cas=overflow_cas),
        ),
        (
            "outbox_same_valid_cas_losing_sibling_rejected_after_winner_install",
            lambda: validate_committed_outbox_variant(
                sibling_outbox,
                commit_receipt=sibling_commit_receipt,
                exact_payload=sibling_exact_payload,
                expected_artifact_digest=committed_outbox_artifact_digest(
                    sibling_outbox
                ),
            ),
        ),
        (
            "outbox_resealed_foreign_cas_rejected",
            lambda: validate_committed_outbox_variant(foreign_cas_outbox),
        ),
        (
            "outbox_resealed_payload_swap_rejected",
            lambda: validate_committed_outbox_variant(payload_swapped_outbox),
        ),
        (
            "outbox_payload_length_claim_tamper_rejected",
            lambda: validate_committed_outbox_variant(length_tampered_outbox),
        ),
        (
            "outbox_resealed_split_write_prior_head_rejected",
            lambda: validate_committed_outbox_variant(
                commit_receipt=split_write_commit_receipt
            ),
        ),
        (
            "outbox_resealed_forged_commit_receipt_rejected",
            lambda: validate_committed_outbox_variant(
                commit_receipt=forged_commit_receipt
            ),
        ),
        (
            "dispatch_resealed_boundary_clock_restart_rejected",
            lambda: validate_dispatch_variant(restarted_dispatch),
        ),
        (
            "dispatch_resealed_attempt_substitution_rejected",
            lambda: validate_dispatch_variant(altered_dispatch_attempt),
        ),
        (
            "dispatch_resealed_transport_rebinding_rejected",
            lambda: validate_dispatch_variant(
                rebound_dispatch,
                expected_context_artifact_digest=(
                    dispatch_artifact_digest(rebound_dispatch)
                ),
            ),
        ),
        (
            "dispatch_resealed_gate_epoch_substitution_rejected",
            lambda: validate_dispatch_variant(
                regated_dispatch,
                expected_context_artifact_digest=(
                    dispatch_artifact_digest(regated_dispatch)
                ),
            ),
        ),
        (
            "dispatch_actual_payload_swap_rejected",
            lambda: validate_dispatch_variant(
                evidence.drain_fact.dispatch_context,
                exact_payload=b"synthetic-hostile-dispatch-payload",
            ),
        ),
        (
            "dispatch_resealed_payload_length_tamper_rejected",
            lambda: validate_dispatch_variant(altered_dispatch_length),
        ),
    ):
        _expect_rejection(label, action, accepted)

    _expect_rejection(
        "forged_outbox_bytes_drain_rejected",
        lambda: boundary.start_external_drain(
            release=replace(evidence.release, outbox_item=forged_outbox),
            actual_dispatch_payload=evidence.release.outbox_item.complete_payload,
            dispatch_context=evidence.drain_fact.dispatch_context,
            expected_dispatch_destination_cut=(
                evidence.drain_fact.expected_dispatch_destination_cut
            ),
            expected_dispatch_context_artifact_digest=(
                evidence.drain_fact.dispatch_context_artifact_digest
            ),
            receiver_dedup_retry_proof=None,
            commit_time=evidence.plan.boundary_deadlines[
                0
            ].boundary_latest_server_activation_at
            + 6,
        ),
        accepted,
    )
    forged_receipt = replace(
        evidence.release.release_receipt,
        output_slot=evidence.release.release_receipt.output_slot + 1,
    )
    _expect_rejection(
        "forged_release_receipt_drain_rejected",
        lambda: boundary.start_external_drain(
            release=replace(
                evidence.release,
                release_receipt=forged_receipt,
            ),
            actual_dispatch_payload=evidence.release.outbox_item.complete_payload,
            dispatch_context=evidence.drain_fact.dispatch_context,
            expected_dispatch_destination_cut=(
                evidence.drain_fact.expected_dispatch_destination_cut
            ),
            expected_dispatch_context_artifact_digest=(
                evidence.drain_fact.dispatch_context_artifact_digest
            ),
            receiver_dedup_retry_proof=None,
            commit_time=evidence.plan.boundary_deadlines[
                0
            ].boundary_latest_server_activation_at
            + 6,
        ),
        accepted,
    )
    forged_item_identity = replace(
        evidence.release.outbox_item,
        stable_item_id=_uuid_for(("forged-outbox-item",)),
    )
    _expect_rejection(
        "forged_outbox_identity_drain_rejected",
        lambda: boundary.start_external_drain(
            release=replace(
                evidence.release,
                outbox_item=forged_item_identity,
            ),
            actual_dispatch_payload=evidence.release.outbox_item.complete_payload,
            dispatch_context=evidence.drain_fact.dispatch_context,
            expected_dispatch_destination_cut=(
                evidence.drain_fact.expected_dispatch_destination_cut
            ),
            expected_dispatch_context_artifact_digest=(
                evidence.drain_fact.dispatch_context_artifact_digest
            ),
            receiver_dedup_retry_proof=None,
            commit_time=evidence.plan.boundary_deadlines[
                0
            ].boundary_latest_server_activation_at
            + 6,
        ),
        accepted,
    )
    forged_read_chain_item = replace(
        evidence.release.outbox_item,
        read_authorization_decision_digest="0" * 64,
    )
    _expect_rejection(
        "outbox_read_decision_chain_substitution_drain_rejected",
        lambda: boundary.start_external_drain(
            release=replace(
                evidence.release,
                outbox_item=forged_read_chain_item,
            ),
            actual_dispatch_payload=evidence.release.outbox_item.complete_payload,
            dispatch_context=evidence.drain_fact.dispatch_context,
            expected_dispatch_destination_cut=(
                evidence.drain_fact.expected_dispatch_destination_cut
            ),
            expected_dispatch_context_artifact_digest=(
                evidence.drain_fact.dispatch_context_artifact_digest
            ),
            receiver_dedup_retry_proof=None,
            commit_time=evidence.plan.boundary_deadlines[
                0
            ].boundary_latest_server_activation_at
            + 6,
        ),
        accepted,
    )
    _expect_rejection(
        "opaque_ambiguous_retry_proof_rejected",
        lambda: boundary.start_external_drain(
            release=evidence.release,
            actual_dispatch_payload=evidence.release.outbox_item.complete_payload,
            dispatch_context=evidence.drain_fact.dispatch_context,
            expected_dispatch_destination_cut=(
                evidence.drain_fact.expected_dispatch_destination_cut
            ),
            expected_dispatch_context_artifact_digest=(
                evidence.drain_fact.dispatch_context_artifact_digest
            ),
            receiver_dedup_retry_proof=hashlib.sha256(b"opaque-proof").hexdigest(),
            commit_time=evidence.plan.boundary_deadlines[
                0
            ].boundary_latest_server_activation_at
            + 6,
        ),
        accepted,
    )

    activation_transition_count = next(
        index
        for index, transition in enumerate(
            boundary_snapshot.transitions,
            start=1,
        )
        if transition.transition_kind == "ACTIVATE_PREPARED_BOUNDARY_GRANT"
    )
    live_snapshot = _snapshot_prefix(
        boundary_snapshot,
        activation_transition_count,
    )
    live_objects = _tuple_map(live_snapshot.objects)
    activation_transition = live_snapshot.transitions[-1]
    activation_receipt = live_objects[
        activation_transition.specialized_receipt_digests[1]
    ]
    _require(
        isinstance(
            activation_receipt,
            TrustedDeliveryBoundaryGrantActivationReceipt,
        ),
        "live fixture activation receipt is absent",
    )
    activation_fact = live_objects[activation_receipt.activation_fact_digest]
    activation_entry = live_objects[activation_receipt.installed_entry_head_digest]
    _require(
        isinstance(activation_fact, TrustedDeliveryBoundaryGrantActivationFact)
        and isinstance(
            activation_entry,
            TrustedDeliveryBoundaryGrantStateHead,
        ),
        "live fixture activation fact or entry is absent",
    )
    live_boundary = TrustedDeliveryBoundary(evidence.plan.boundary_members[0])
    live_boundary.store = (
        AtomicAuthorityStore._from_validated_counterfactual_snapshot_for_test(
            live_snapshot,
            trusted_clock_sample=(
                _fixture_continuous_recovery_clock_sample(live_snapshot)
            ),
        )
    )
    live_activation = BoundaryActivationResult(
        fact=activation_fact,
        activation_receipt=activation_receipt,
        installed_entry=activation_entry,
    )
    _expect_rejection(
        "reservation_scope_outside_grant_rejected",
        lambda: live_boundary.create_reservation(
            activation=live_activation,
            payload=b"hostile scope payload",
            read_scope=replace(
                evidence.plan.boundary_members[0].read_scope,
                scope_digest=hashlib.sha256(b"unauthorized-scope").hexdigest(),
            ),
            boundary_membership=(evidence.plan.boundary_members[0].scope_membership),
            read_authorization_decision=evidence.read_authorization_decision,
            retained_authorization_cut=evidence.retained_read_authorization_cut,
            release_recipient_context=(
                evidence.release.reservation.release_recipient_context
            ),
            expected_release_transport_context=(
                evidence.release.reservation.expected_release_transport_context
            ),
            expected_release_context_artifact_digest=(
                release_recipient_artifact_digest(
                    evidence.release.reservation.release_recipient_context
                )
            ),
            release_idempotency_key=_uuid_for(("hostile-scope-request",)),
            commit_time=evidence.plan.boundary_deadlines[
                0
            ].boundary_latest_server_activation_at
            + 2,
        ),
        accepted,
    )
    _expect_rejection(
        "reservation_read_decision_authentication_tag_substitution_rejected",
        lambda: live_boundary.create_reservation(
            activation=live_activation,
            payload=b"hostile decision seal payload",
            read_scope=evidence.plan.boundary_members[0].read_scope,
            boundary_membership=(evidence.plan.boundary_members[0].scope_membership),
            read_authorization_decision=replace(
                evidence.read_authorization_decision,
                fixture_authentication_tag="0" * 64,
            ),
            retained_authorization_cut=evidence.retained_read_authorization_cut,
            release_recipient_context=(
                evidence.release.reservation.release_recipient_context
            ),
            expected_release_transport_context=(
                evidence.release.reservation.expected_release_transport_context
            ),
            expected_release_context_artifact_digest=(
                release_recipient_artifact_digest(
                    evidence.release.reservation.release_recipient_context
                )
            ),
            release_idempotency_key=_uuid_for(("hostile-decision-seal-request",)),
            commit_time=evidence.plan.boundary_deadlines[
                0
            ].boundary_latest_server_activation_at
            + 2,
        ),
        accepted,
    )
    history_server = ObserverAuthorizationServer()
    history_server.store = (
        AtomicAuthorityStore._from_validated_counterfactual_snapshot_for_test(
            evidence.server_snapshot,
            trusted_clock_sample=(
                _fixture_continuous_recovery_clock_sample(evidence.server_snapshot)
            ),
        )
    )
    valid_history_decision = history_server.authorize_read(
        evidence.capability_evidence,
        live_transport_context=(
            evidence.capability_evidence.verified_transport_context
        ),
        read_scope=history_member.read_scope,
        boundary_membership=history_member.scope_membership,
        expected_boundary_identity=(
            history_member.boundary_principal,
            history_member.boundary_instance,
            history_member.deadline_policy_id,
        ),
        observer_instance=OBSERVER_INSTANCE,
        caller_operation_id=_uuid_for(("observer-read", "history", 1)),
        trusted_time=111,
    )

    def validate_history_decision_variant(
        decision: SealedObserverReadAuthorizationDecision,
        *,
        fixture_key: Any = _READ_DECISION_SEAL_KEY,
    ) -> None:
        try:
            validate_read_decision(
                decision,
                scope=history_member.read_scope,
                membership=history_member.scope_membership,
                expected_boundary_identity=(
                    history_member.boundary_principal,
                    history_member.boundary_instance,
                    history_member.deadline_policy_id,
                ),
                expected_observer_identity=(
                    evidence.capability_evidence.capability.observer_principal,
                    OBSERVER_INSTANCE,
                ),
                expected_authorization_audience=(
                    history_member.read_scope.authorization_audience
                ),
                expected_authorization_cut=_retain_read_authorization_cut(
                    valid_history_decision
                ),
                expected_issuer_identity=(
                    SERVER_PRINCIPAL,
                    SERVER_KEY_ID,
                    SERVER_STATE_INCARNATION,
                ),
                fixture_key=fixture_key,
            )
        except BridgeValidationError as exc:
            raise ProbeError("history read-decision variant rejected") from exc

    def seal_and_validate_history_mutation(mutation: dict[str, Any]) -> None:
        try:
            hostile_decision = seal_read_decision(
                replace(valid_history_decision, **mutation),
                fixture_key=_READ_DECISION_SEAL_KEY,
            )
        except BridgeValidationError as exc:
            raise ProbeError("history read-decision mutation rejected") from exc
        validate_history_decision_variant(hostile_decision)

    for label, mutation in (
        (
            "history_request_digest_scope_substitution_rejected",
            {"history_request_digest": "0" * 64},
        ),
        (
            "history_observer_principal_substitution_rejected",
            {"observer_principal": "forged-observer"},
        ),
        (
            "history_security_epoch_above_safe_integer_rejected",
            {"security_epoch": MAX_SAFE_INTEGER + 1},
        ),
        (
            "history_revocation_epoch_above_safe_integer_rejected",
            {"revocation_epoch": MAX_SAFE_INTEGER + 1},
        ),
        (
            "history_invalid_unicode_scalar_rejected",
            {"observer_principal": "\ud800"},
        ),
    ):
        _expect_rejection(
            label,
            lambda mutation=mutation: seal_and_validate_history_mutation(mutation),
            accepted,
        )
    _expect_rejection(
        "history_fixture_hmac_short_key_rejected",
        lambda: validate_history_decision_variant(
            valid_history_decision,
            fixture_key=b"x" * 31,
        ),
        accepted,
    )
    _expect_rejection(
        "history_fixture_hmac_mutable_key_rejected",
        lambda: validate_history_decision_variant(
            valid_history_decision,
            fixture_key=bytearray(_READ_DECISION_SEAL_KEY),
        ),
        accepted,
    )
    _expect_rejection(
        "reservation_valid_cross_scope_decision_chain_substitution_rejected",
        lambda: live_boundary.create_reservation(
            activation=live_activation,
            payload=b"hostile cross-scope decision payload",
            read_scope=history_member.read_scope,
            boundary_membership=history_member.scope_membership,
            read_authorization_decision=valid_history_decision,
            retained_authorization_cut=_retain_read_authorization_cut(
                valid_history_decision
            ),
            release_recipient_context=(
                evidence.release.reservation.release_recipient_context
            ),
            expected_release_transport_context=(
                evidence.release.reservation.expected_release_transport_context
            ),
            expected_release_context_artifact_digest=(
                release_recipient_artifact_digest(
                    evidence.release.reservation.release_recipient_context
                )
            ),
            release_idempotency_key=_uuid_for(
                ("hostile-cross-scope-decision-request",)
            ),
            commit_time=evidence.plan.boundary_deadlines[
                0
            ].boundary_latest_server_activation_at
            + 2,
        ),
        accepted,
    )

    def reuse_single_release_read_decision() -> None:
        replay_boundary = TrustedDeliveryBoundary(evidence.plan.boundary_members[0])
        replay_boundary.store = (
            AtomicAuthorityStore._from_validated_counterfactual_snapshot_for_test(
                live_snapshot,
                trusted_clock_sample=(
                    _fixture_continuous_recovery_clock_sample(live_snapshot)
                ),
            )
        )
        replay_boundary.create_reservation(
            activation=live_activation,
            payload=b"first decision-bound payload",
            read_scope=evidence.plan.boundary_members[0].read_scope,
            boundary_membership=(evidence.plan.boundary_members[0].scope_membership),
            read_authorization_decision=evidence.read_authorization_decision,
            retained_authorization_cut=evidence.retained_read_authorization_cut,
            release_recipient_context=(
                evidence.release.reservation.release_recipient_context
            ),
            expected_release_transport_context=(
                evidence.release.reservation.expected_release_transport_context
            ),
            expected_release_context_artifact_digest=(
                release_recipient_artifact_digest(
                    evidence.release.reservation.release_recipient_context
                )
            ),
            release_idempotency_key=_uuid_for(("decision-use", 1)),
            commit_time=evidence.plan.boundary_deadlines[
                0
            ].boundary_latest_server_activation_at
            + 2,
        )
        replay_boundary.create_reservation(
            activation=live_activation,
            payload=b"second decision-bound payload",
            read_scope=evidence.plan.boundary_members[0].read_scope,
            boundary_membership=(evidence.plan.boundary_members[0].scope_membership),
            read_authorization_decision=evidence.read_authorization_decision,
            retained_authorization_cut=evidence.retained_read_authorization_cut,
            release_recipient_context=(
                evidence.release.reservation.release_recipient_context
            ),
            expected_release_transport_context=(
                evidence.release.reservation.expected_release_transport_context
            ),
            expected_release_context_artifact_digest=(
                release_recipient_artifact_digest(
                    evidence.release.reservation.release_recipient_context
                )
            ),
            release_idempotency_key=_uuid_for(("decision-use", 2)),
            commit_time=evidence.plan.boundary_deadlines[
                0
            ].boundary_latest_server_activation_at
            + 3,
        )

    _expect_rejection(
        "single_release_read_decision_reuse_rejected",
        reuse_single_release_read_decision,
        accepted,
    )

    def attempt_expired_terminal(
        *,
        expiry: bool,
        commit_time: int,
    ) -> None:
        server = ObserverAuthorizationServer()
        server.store = (
            AtomicAuthorityStore._from_validated_counterfactual_snapshot_for_test(
                server_snapshot,
                trusted_clock_sample=(
                    _fixture_continuous_recovery_clock_sample(server_snapshot)
                ),
            )
        )
        server.terminate(
            evidence.plan.stable_registry_key,
            terminal_reason="EXPIRED",
            actor_or_event="trusted-clock-expiry",
            policy_rule_digest=_SERVER_EXPIRY_POLICY_RULE_DIGEST,
            policy_inputs_digest=_SERVER_EXPIRY_POLICY_INPUTS_DIGEST,
            authority_source_receipt_digest=(
                _SERVER_EXPIRY_AUTHORITY_SOURCE_RECEIPT_DIGEST
            ),
            commit_time=commit_time,
            expiry=expiry,
        )

    _expect_rejection(
        "expired_without_expiry_predicate_rejected",
        lambda: attempt_expired_terminal(expiry=False, commit_time=200),
        accepted,
    )
    _expect_rejection(
        "expired_before_elapsed_deadline_rejected",
        lambda: attempt_expired_terminal(expiry=True, commit_time=199),
        accepted,
    )

    descriptor = next(
        item
        for item in _tuple_map(server_snapshot.objects).values()
        if isinstance(item, ObserverDescriptor)
    )
    for cut in FAULT_CUTS[:-1]:

        def exercise_preapply_fault(cut_name: str = cut) -> None:
            server = ObserverAuthorizationServer()
            try:
                server.genesis(
                    descriptor,
                    manifest=evidence.default_deny_manifest,
                    commit_time=90,
                    fault_cut=cut_name,
                )
            except ProbeError:
                _require(
                    server.store.snapshot.snapshot_version == 0,
                    "pre-apply fault published partial state",
                )
                raise

        _expect_rejection(
            f"atomic_fault_{cut.lower()}_rejected_without_publish",
            exercise_preapply_fault,
            accepted,
        )

    def exercise_ack_loss() -> None:
        server = ObserverAuthorizationServer()
        recovery_authority = server._persistence_recovery_authority
        zombie_writer = server.store
        try:
            server.genesis(
                descriptor,
                manifest=evidence.default_deny_manifest,
                commit_time=90,
                fault_cut="AFTER_POINTER_APPLY_BEFORE_ACK",
            )
        except ProbeError:
            _require(
                server.store.snapshot.snapshot_version == 1,
                "post-apply acknowledgement loss erased the durable winner",
            )
            durable_snapshot = server.store.snapshot
            durable_root = server.store.persistence_root
            _validate_atomic_snapshot(durable_snapshot)
            for sample, lease in ((90, 90), (90, 10_091)):
                try:
                    recovery_authority.issue_admission(
                        trusted_recovery_clock_sample=sample,
                        writer_exclusive_not_after=lease,
                    )
                except ProbeError:
                    pass
                else:
                    raise ProbeError(
                        "recovery authority accepted an expired or excessive lease"
                    )
            admission = recovery_authority.issue_admission(
                trusted_recovery_clock_sample=90,
                writer_exclusive_not_after=10_000,
            )
            try:
                setattr(admission, "writer_exclusive_not_after", MAX_SAFE_INTEGER)
            except (AttributeError, TypeError):
                pass
            else:
                raise ProbeError("recovery admission fields are mutable")
            forged_admissions = (
                ("copied", replace(admission)),
                (
                    "capability",
                    replace(admission, _capability=object()),
                ),
                (
                    "snapshot root",
                    replace(
                        admission,
                        snapshot_root=hashlib.sha256(
                            b"forged-recovery-root"
                        ).hexdigest(),
                    ),
                ),
                (
                    "snapshot version",
                    replace(
                        admission,
                        snapshot_version=admission.snapshot_version + 1,
                    ),
                ),
                (
                    "recovery ID",
                    replace(
                        admission,
                        recovery_id=_uuid_for(("forged-recovery", 1)),
                    ),
                ),
                (
                    "recovery sequence",
                    replace(
                        admission,
                        recovery_sequence=admission.recovery_sequence + 1,
                    ),
                ),
                (
                    "writer epoch",
                    replace(
                        admission,
                        writer_epoch=admission.writer_epoch + 1,
                    ),
                ),
                (
                    "trusted sample",
                    replace(
                        admission,
                        trusted_recovery_clock_sample=91,
                    ),
                ),
                (
                    "writer lease",
                    replace(
                        admission,
                        writer_exclusive_not_after=9_999,
                    ),
                ),
                (
                    "clock source",
                    replace(
                        admission,
                        _trusted_clock_source=lambda: 90,
                    ),
                ),
                (
                    "clock policy",
                    replace(
                        admission,
                        clock_source_policy=("SYNTHETIC_IN_PROCESS_MONOTONIC_CALLBACK"),
                    ),
                ),
            )
            for label, forged_admission in forged_admissions:
                try:
                    AtomicAuthorityStore.recover(
                        durable_snapshot,
                        admission=forged_admission,
                    )
                except ProbeError:
                    pass
                else:
                    raise ProbeError(f"recovery admitted a forged {label} admission")
            sibling = replace(
                durable_snapshot,
                authority_key_id="body-service:key:foreign",
            )
            try:
                AtomicAuthorityStore.recover(
                    sibling,
                    admission=admission,
                )
            except ProbeError:
                pass
            else:
                raise ProbeError("recovery admitted a sibling durable snapshot")
            recovered_store = AtomicAuthorityStore.recover(
                durable_snapshot,
                admission=admission,
            )
            _require(
                recovered_store.persistence_root == durable_root
                and recovered_store.snapshot == durable_snapshot,
                "recovery changed the durable winner",
            )
            server.store = recovered_store
            transition_count = len(server.store.snapshot.transitions)
            server.genesis(
                descriptor,
                manifest=evidence.default_deny_manifest,
                commit_time=90,
            )
            _require(
                len(server.store.snapshot.transitions) == transition_count == 1
                and server.store.persistence_root == durable_root,
                "post-recovery exact retry was not state-free",
            )
            try:
                zombie_writer.set_trusted_clock_for_test(90)
            except ProbeError:
                pass
            else:
                raise ProbeError("recovery left the pre-crash writer live")
            try:
                AtomicAuthorityStore.recover(
                    durable_snapshot,
                    admission=admission,
                )
            except ProbeError:
                pass
            else:
                raise ProbeError("recovery admission was replayable")
            raise

    _expect_rejection(
        "atomic_ack_loss_preserves_winner",
        exercise_ack_loss,
        accepted,
    )

    rollback_store = (
        AtomicAuthorityStore._from_validated_counterfactual_snapshot_for_test(
            server_snapshot,
            trusted_clock_sample=(
                _fixture_continuous_recovery_clock_sample(server_snapshot)
            ),
        )
    )
    _expect_rejection(
        "trusted_clock_rollback_rejected",
        lambda: rollback_store.set_trusted_clock_for_test(0),
        accepted,
    )

    commitment_mutations = bridge_commitment_suite_mutation_report()
    _require(
        commitment_mutations["total_mutations_executed"]
        == commitment_mutations["total_mutations_rejected"],
        "bridge commitment suite has a surviving mutation",
    )
    accepted.extend(
        (
            "bridge_commitment_every_declared_leaf_mutation_rejected",
            "bridge_commitment_sequence_order_mutations_rejected",
            "bridge_commitment_missing_top_level_members_rejected",
            "bridge_commitment_unknown_member_rejected",
            "bridge_commitment_digest_substitution_rejected",
        )
    )

    _require(
        len(accepted) == len(set(accepted)),
        "hostile witness labels are duplicated",
    )
    return tuple(accepted)


def _self_test_smoke() -> None:
    evidence = _build_smoke_evidence()
    _validate_explicit_type_registry(evidence)
    _validate_atomic_snapshot(evidence.server_snapshot)
    for snapshot in evidence.boundary_snapshots:
        _validate_atomic_snapshot(snapshot)
    _require(
        evidence.drain_disposition.outcome == "DELIVERED",
        "smoke evidence did not reach a definitive transport outcome",
    )
    _require(
        len(_run_hostile_tests(evidence)) >= 40,
        "hostile suite did not exercise the bounded attack matrix",
    )
    result = build_result()
    _require(
        result["counts"]
        == {
            "server_transitions": 3,
            "boundary_transitions": 10,
            "boundaries": 2,
            "released_items": 1,
            "sealed_capability_issuances": 1,
            "authorized_read_decisions": 1,
            "exact_read_admission_retries": 1,
            "hostile_rejections": 169,
            "release_linearization_witnesses": 16,
            "registered_staged_artifact_types": 71,
            "closed_read_route_classes": 5,
        },
        "observer authorization exact count baseline drifted",
    )
    _require(
        result["shared_bridge_commitment"]["mutation_report"][
            "total_mutations_executed"
        ]
        == result["shared_bridge_commitment"]["mutation_report"][
            "total_mutations_rejected"
        ]
        == 672
        and result["shared_bridge_commitment"]["profile_mutation_report"][
            "total_mutations_executed"
        ]
        == result["shared_bridge_commitment"]["profile_mutation_report"][
            "total_mutations_rejected"
        ]
        == 310,
        "observer authorization bridge mutation baseline drifted",
    )
    validate_result(
        json.loads(json.dumps(result, separators=(",", ":"), sort_keys=True))
    )


def build_result() -> dict[str, Any]:
    validate_bridge_canonical_type_system()
    commitment_suite = bridge_commitment_suite()
    commitment_suite_digest = bridge_commitment_suite_digest()
    commitment_suite_digest_domain = bridge_commitment_suite_digest_domain()
    commitment_mutations = bridge_commitment_suite_mutation_report()
    bridge_profile = observer_read_capture_bridge_profile()
    validate_observer_read_capture_bridge_profile(bridge_profile)
    profile_mutations = observer_read_capture_bridge_profile_mutation_report()
    _require(
        bridge_profile["canonical_commitment"]
        == {
            "suite": commitment_suite,
            "suite_digest": commitment_suite_digest,
            "suite_digest_domain": commitment_suite_digest_domain,
        }
        and profile_mutations["total_mutations_executed"]
        == profile_mutations["total_mutations_rejected"],
        "shared bridge profile or its commitment triple differs",
    )
    evidence = _build_smoke_evidence()
    reached_artifact_type_ids = _validate_explicit_type_registry(evidence)
    release_linearization_witnesses = _run_release_linearization_tests(evidence)
    hostile_rejections = _run_hostile_tests(evidence)
    return {
        "schema_version": SCHEMA_VERSION,
        "probe": "observer_authorization",
        "claim_boundary": {
            "status": "synthetic_pre_ratification_non_normative",
            "wire_implementation": False,
            "interoperability": "NOT RUN",
            "release_readiness": "NOT RUN",
            "live_transport_principal_binding": "NOT RUN",
            "capability_issuer_cryptographic_qualification": "NOT RUN",
            "external_revocation_propagation": "NOT RUN",
            "external_transport_enqueue_evidence": (
                "synthetic_in_process_coordinator_record_only"
            ),
            "external_transport_enqueue_durability": "NOT RUN",
            "capability_seal_evidence": "synthetic_hmac_fixture_only",
            "read_decision_seal_evidence": "synthetic_hmac_fixture_only",
            "read_decision_authority_effect": NO_FUTURE_AUTHORITY,
            "direct_server_transition_kinds": (
                "OBSERVER_AUTHORIZATION_STATE_GENESIS_FROM_SESSION_CREATION",
                "ATTACH_NEW_GRANT_LINEAGE",
                "ACTIVATE_PENDING_GRANT",
                "TERMINATE_GRANT",
            ),
            "direct_boundary_transition_kinds": (
                "RELEASE_STATE_GENESIS_FROM_UNINITIALIZED",
                "PREPARE_BOUNDARY_GRANT",
                "ACTIVATE_PREPARED_BOUNDARY_GRANT",
                "CREATE_TRUSTED_DELIVERY_RELEASE_RESERVATION",
                "COMMIT_TRUSTED_DELIVERY_RELEASE_OUTBOX",
                "START_EXTERNAL_TRANSPORT_DRAIN",
                "RESOLVE_EXTERNAL_TRANSPORT_DRAIN",
                "TERMINATE_BOUNDARY_GRANT",
            ),
        },
        "review_lenses": (
            "canonical_exact_type_identity",
            "sealed_issuer_and_transport_principal_provenance",
            "session_security_revocation_and_recovery_currentness",
            "read_only_surface_and_actuation_separation",
            "deterministic_reproducible_evidence",
            "temporal_clock",
            "distributed_transport",
        ),
        "shared_bridge_commitment": {
            "profile": bridge_profile,
            "profile_digest": observer_read_capture_bridge_profile_digest(),
            "profile_digest_domain": (
                observer_read_capture_bridge_profile_digest_domain()
            ),
            "profile_mutation_report": profile_mutations,
            "suite": commitment_suite,
            "suite_digest": commitment_suite_digest,
            "suite_digest_domain": commitment_suite_digest_domain,
            "mutation_report": commitment_mutations,
        },
        "counts": {
            "server_transitions": len(evidence.server_snapshot.transitions),
            "boundary_transitions": sum(
                len(snapshot.transitions) for snapshot in evidence.boundary_snapshots
            ),
            "boundaries": len(evidence.boundary_snapshots),
            "released_items": 1,
            "sealed_capability_issuances": 1,
            "authorized_read_decisions": 1,
            "exact_read_admission_retries": 1,
            "hostile_rejections": len(hostile_rejections),
            "release_linearization_witnesses": len(release_linearization_witnesses),
            "registered_staged_artifact_types": len(reached_artifact_type_ids),
            "closed_read_route_classes": len(READ_ROUTE_CLASS_SHAPES),
        },
        "invariant_witnesses": {
            "atomic_release_linearization": release_linearization_witnesses,
            "stable_registry_key": _digest(evidence.plan.stable_registry_key),
            "full_boundary_key": _digest(
                evidence.server_activation.installed_ledger_head.full_boundary_key
            ),
            "server_snapshot": _digest(evidence.server_snapshot),
            "boundary_snapshots": tuple(
                _digest(snapshot) for snapshot in evidence.boundary_snapshots
            ),
            "release_receipt": _digest(evidence.release.release_receipt),
            "complete_outbox_item": _digest(evidence.release.outbox_item),
            "transport_disposition": _digest(evidence.drain_disposition),
            "bridge_commitment_suite": commitment_suite_digest,
            "default_deny_manifest": _digest(evidence.default_deny_manifest),
            "synthetic_verified_transport_principal_context": _digest(
                evidence.capability_evidence.verified_transport_context
            ),
            "observer_read_capability": _digest(
                evidence.capability_evidence.capability
            ),
            "observer_read_capability_seal": _digest(evidence.capability_evidence.seal),
            "observer_read_capability_issuer_snapshot": _digest(
                evidence.capability_evidence.issuer_snapshot
            ),
            "canonical_read_scope": evidence.release.reservation.canonical_scope_digest,
            "boundary_read_scope_membership": (
                evidence.release.reservation.boundary_scope_membership_digest
            ),
            "sealed_read_authorization_decision": _digest(
                evidence.read_authorization_decision
            ),
            "read_authorization_exact_retry": _digest(
                evidence.read_authorization_exact_retry
            ),
            "release_authority_recheck": (
                evidence.release.reservation.release_authority_recheck_digest
            ),
            "delivery_chain_retained_at_disposition": _semantic_digest(
                "ncp.b01.ObserverReadReleaseDispositionBinding@1",
                (
                    evidence.drain_disposition.canonical_scope_digest,
                    evidence.drain_disposition.boundary_scope_membership_digest,
                    evidence.drain_disposition.read_authorization_decision_digest,
                    evidence.drain_disposition.release_authority_recheck_digest,
                ),
            ),
            "hostile_rejection_labels": hostile_rejections,
            "registered_staged_artifact_type_ids": reached_artifact_type_ids,
        },
        "structural_future_obligations": (
            "server renewal direct scenario",
            "boundary transport-quiescence direct scenario",
            "authenticated server and boundary clock restart",
            "live external transport principal rotation and revocation campaign",
            "multi-entry default-deny manifest and concurrent connection campaign",
            "bulk dynamic-cardinality terminalization",
            "reattachment with distributed closure authority",
            "observer admission selector allocation",
            "distributed authorization closure aggregation",
            "transport quiescence aggregation",
            "receiver admission cut",
            "consumer semantic capture selectors",
        ),
        "prisoma_gate": {
            "status": "BLOCKED",
            "candidate_rows": 1,
            "eligible_rows": 0,
            "estimator_calls": 0,
        },
    }


def validate_result(value: Any) -> None:
    _require(
        isinstance(value, dict)
        and json.dumps(value, separators=(",", ":"), sort_keys=True)
        == json.dumps(build_result(), separators=(",", ":"), sort_keys=True),
        "observer authorization result differs from deterministic semantic replay",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        _self_test_smoke()
        print("observer authorization self-test: PASS")
        return 0
    json.dump(build_result(), sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
