#!/usr/bin/env python3
"""Shared synthetic observer-read to capture provenance types.

These types are pre-ratification B01 evidence-model artifacts.  The HMAC helper
is deterministic fixture cryptography only.  It is not a wire implementation,
an installed issuer, or external cryptographic qualification.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass, replace
from typing import Any

from bounded_canonical import (
    CanonicalLimits,
    FrozenList,
    FrozenMap,
    FrozenTypeRegistry,
    freeze_owned,
)
from bounded_canonical import (
    canonical_bytes as _bounded_canonical_bytes,
)

MAX_SAFE_INTEGER = 9_007_199_254_740_991
FIXTURE_HMAC_KEY_BYTES = 32
MAX_BRIDGE_PAYLOAD_OCTETS = 1_048_576
MAX_BRIDGE_STRING_OCTETS = 1_048_576
MAX_BRIDGE_CANONICAL_OCTETS = 8_388_608
MAX_BRIDGE_CANONICAL_DEPTH = 64
MAX_BRIDGE_CANONICAL_NODES = 16_384
MAX_BRIDGE_COLLECTION_ITEMS = 4_096
MAX_BRIDGE_ARTIFACT_FIELDS = 128
MAX_BRIDGE_DOMAIN_OCTETS = 128
BRIDGE_DIGEST_PREFIX = b"NCP-B01-OBSERVER-READ-CAPTURE-BRIDGE-V1"
BRIDGE_FRAME_SEPARATOR = b"\x00"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
ROUTE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
BRIDGE_DIGEST_DOMAIN = re.compile(
    r"^ncp\.b01\.bridge\.[A-Za-z][A-Za-z0-9]*(?:[._-][A-Za-z0-9]+)*@1$"
)
CANONICAL_UUID4 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

READ_OPERATIONS = ("history_query", "subscribe")
READ_ROUTE_CLASS_SHAPES: dict[str, tuple[str, str]] = {
    "ACTION_COMMAND_PROPOSAL": ("action", "CommandFrame"),
    "OBSERVATION_COMMAND_DISPOSITION": ("observation", "CommandDisposition"),
    "OBSERVATION_FRAME": ("observation", "ObservationFrame"),
    "PERCEPTION_PROJECTED_OBSERVATION": ("perception", "ObservationFrame"),
    "PERCEPTION_SENSOR_FRAME": ("perception", "SensorFrame"),
}
_READ_ROUTE_CLASS_FAMILIES: dict[str, tuple[str, bool]] = {
    "ACTION_COMMAND_PROPOSAL": ("command", True),
    "OBSERVATION_COMMAND_DISPOSITION": ("observation", False),
    "OBSERVATION_FRAME": ("observation", False),
    "PERCEPTION_PROJECTED_OBSERVATION": ("sensor", True),
    "PERCEPTION_SENSOR_FRAME": ("sensor", True),
}
SOURCE_SESSION_KINDS = frozenset({"NCP_SESSION", "PLANT_CONTROL", "SIMULATION_SERVICE"})
LIVE_ROUTE_DOMAIN = "NCP_LIVE_ROUTE"
HISTORY_CONTENT_DOMAIN = "CONTENT_ADDRESSED_HISTORY_DOMAIN"
NO_FUTURE_AUTHORITY = "PREFLIGHT_ONLY_RELEASE_RECHECK_REQUIRED"
_AUTHORITY_SENTINELS = frozenset(
    {
        "anonymous",
        "default",
        "none",
        "null",
        "unauthenticated",
        "unknown",
        "unspecified",
        "zero",
        "00000000-0000-0000-0000-000000000000",
    }
)
_BRIDGE_DATACLASS_TYPE_REFS: dict[type[Any], str] = {}


class BridgeValidationError(ValueError):
    """A shared observer-read/capture bridge artifact is not canonical."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BridgeValidationError(message)


_BRIDGE_CANONICAL_LIMITS = CanonicalLimits(
    max_output_bytes=MAX_BRIDGE_CANONICAL_OCTETS,
    max_depth=MAX_BRIDGE_CANONICAL_DEPTH,
    max_nodes=MAX_BRIDGE_CANONICAL_NODES,
    max_collection_items=MAX_BRIDGE_COLLECTION_ITEMS,
    max_artifact_fields=MAX_BRIDGE_ARTIFACT_FIELDS,
    max_string_bytes=MAX_BRIDGE_STRING_OCTETS,
    max_payload_bytes=MAX_BRIDGE_PAYLOAD_OCTETS,
    max_aggregate_scalar_bytes=MAX_BRIDGE_CANONICAL_OCTETS,
    min_integer=-MAX_SAFE_INTEGER,
    max_integer=MAX_SAFE_INTEGER,
)


def _canonical_bytes(value: Any) -> bytes:
    """Commit one structurally immutable bridge value to bounded canonical bytes."""

    return _bounded_canonical_bytes(
        value,
        style="bridge",
        limits=_BRIDGE_CANONICAL_LIMITS,
        type_ids=_BRIDGE_DATACLASS_TYPE_REFS,
        error_type=BridgeValidationError,
    )


def _freeze_owned_bridge_json(value: Any) -> Any:
    """Freeze one unpublished, module-owned JSON authoring value."""

    return freeze_owned(
        value,
        limits=_BRIDGE_CANONICAL_LIMITS,
        error_type=BridgeValidationError,
        allowed_dataclass_types=_BRIDGE_DATACLASS_TYPE_REFS,
        allow_dataclasses=True,
    )


def _owned_json_domain_digest(domain: str, value: Any) -> str:
    """Digest module-owned authoring JSON only after immutable conversion."""

    return _domain_digest(domain, _freeze_owned_bridge_json(value))


def _registered_artifact_projection(
    value: Any,
    *,
    expected_type: type[Any],
    excluded_fields: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Read each field once from one exact, revalidated bridge artifact."""

    _require(
        type(value) is expected_type,
        "bridge artifact projection instance type is not exact",
    )
    _require(
        type(excluded_fields) is frozenset
        and all(type(name) is str for name in excluded_fields),
        "bridge artifact projection exclusion set is not exact",
    )
    registry = _BRIDGE_DATACLASS_TYPE_REFS
    _require(
        type(registry) is FrozenTypeRegistry,
        "bridge artifact registry is not initialized or exact",
    )
    try:
        expected_stable_id = registry[expected_type]
        stable_id, field_snapshot = registry.snapshot_artifact_view(value)
    except (KeyError, ValueError) as error:
        raise BridgeValidationError(
            "bridge artifact registry snapshot is unavailable"
        ) from error
    _require(
        stable_id is expected_stable_id,
        "bridge artifact snapshot has a different stable type identity",
    )
    field_names = tuple(name for name, _field_value in field_snapshot)
    _require(
        excluded_fields.issubset(field_names),
        "bridge artifact projection excludes an unknown field",
    )
    return {
        name: field_value
        for name, field_value in field_snapshot
        if name not in excluded_fields
    }


def _domain_frame(domain: str, value: Any) -> bytes:
    _require(
        type(domain) is str
        and 0 < len(domain) <= MAX_BRIDGE_DOMAIN_OCTETS
        and domain.isascii(),
        "bridge digest domain is not exact bounded ASCII",
    )
    try:
        domain_bytes = domain.encode("ascii")
    except UnicodeEncodeError as error:
        raise BridgeValidationError("bridge digest domain is not ASCII") from error
    _require(
        0 < len(domain_bytes) <= MAX_BRIDGE_DOMAIN_OCTETS
        and BRIDGE_DIGEST_DOMAIN.fullmatch(domain) is not None,
        "bridge digest domain is not one closed stable @1 domain",
    )
    return (
        BRIDGE_DIGEST_PREFIX
        + BRIDGE_FRAME_SEPARATOR
        + domain_bytes
        + BRIDGE_FRAME_SEPARATOR
        + _canonical_bytes(value)
    )


def _domain_digest(domain: str, value: Any) -> str:
    return hashlib.sha256(_domain_frame(domain, value)).hexdigest()


def _validate_fixture_key(fixture_key: Any) -> None:
    _require(
        type(fixture_key) is bytes and len(fixture_key) == FIXTURE_HMAC_KEY_BYTES,
        "synthetic fixture HMAC key must be exactly 32 immutable bytes",
    )


def _closed_ascii(
    value: Any,
    *,
    label: str,
    maximum_bytes: int,
    allow_empty: bool = False,
    identifier: bool = False,
    authority_bearing: bool = False,
) -> None:
    _require(
        type(value) is str
        and (allow_empty or bool(value))
        and len(value) <= maximum_bytes
        and value.isascii()
        and "*" not in value
        and "\x00" not in value
        and all(0x20 <= ord(character) <= 0x7E for character in value),
        f"{label} is empty, wildcarded, non-ASCII, overlong, or noncanonical",
    )
    if identifier:
        _require(IDENTIFIER.fullmatch(value) is not None, f"{label} is invalid")
    if authority_bearing:
        _require(
            value.casefold() not in _AUTHORITY_SENTINELS,
            f"{label} uses an unknown, default, or zero authority sentinel",
        )


def _authority_identifier(value: Any, *, label: str) -> None:
    _closed_ascii(
        value,
        label=label,
        maximum_bytes=128,
        identifier=True,
        authority_bearing=True,
    )


def _instance_identifier(value: Any, *, label: str) -> None:
    if type(value) is str and CANONICAL_UUID4.fullmatch(value) is not None:
        return
    _authority_identifier(value, label=label)


def _route_segment(
    value: Any,
    *,
    label: str,
    allow_empty: bool = False,
) -> None:
    _closed_ascii(
        value,
        label=label,
        maximum_bytes=64,
        allow_empty=allow_empty,
    )
    if value:
        _require(
            value not in {".", ".."}
            and "." not in value
            and ROUTE_SEGMENT.fullmatch(value) is not None,
            f"{label} is not one exact portable route segment",
        )


def _uuid4(value: Any, *, label: str) -> None:
    _require(
        type(value) is str and CANONICAL_UUID4.fullmatch(value) is not None,
        f"{label} is not one canonical lowercase UUIDv4",
    )


def _digest64(value: Any, *, label: str, authority_bearing: bool = False) -> None:
    _require(
        type(value) is str and HEX64.fullmatch(value) is not None,
        f"{label} is not canonical SHA-256",
    )
    if authority_bearing:
        _require(
            value != "0" * 64,
            f"{label} uses the zero authority sentinel",
        )


def _validate_expected_transport_context(
    context: Any,
    *,
    label: str,
) -> None:
    _require(
        type(context) is tuple
        and len(context) == 3
        and all(type(value) is str for value in context),
        f"{label} is not one exact endpoint, connection, and replay tuple",
    )
    endpoint_profile, connection_instance, replay_domain = context
    _closed_ascii(
        endpoint_profile,
        label=f"{label} endpoint profile",
        maximum_bytes=32,
        identifier=True,
    )
    _instance_identifier(
        connection_instance,
        label=f"{label} connection instance",
    )
    _authority_identifier(
        replay_domain,
        label=f"{label} replay domain",
    )
    _require(
        endpoint_profile == "production-secure",
        f"{label} endpoint profile is not production-secure",
    )


def canonical_read_route(
    *,
    realm: str,
    logical_session_id: str,
    route_class: str,
    channel: str,
) -> str:
    """Return the only admitted NCP data route for one read-scope shape."""

    _route_segment(realm, label="route realm")
    _route_segment(logical_session_id, label="route logical session")
    _closed_ascii(
        route_class,
        label="route class",
        maximum_bytes=64,
        identifier=True,
    )
    family = _READ_ROUTE_CLASS_FAMILIES.get(route_class)
    _require(family is not None, "route class is outside the closed read set")
    family_name, channel_allowed = family
    _route_segment(channel, label="route channel", allow_empty=True)
    _require(
        channel_allowed or channel == "",
        "observation routes cannot carry a channel alias",
    )
    suffix = f"/{channel}" if channel else ""
    return f"{realm}/session/{logical_session_id}/{family_name}{suffix}"


def canonical_history_delivery_domain(
    scope: CanonicalObserverReadScope,
) -> str:
    """Return a non-transport domain for one exact bounded history request."""

    validate_scope(scope)
    _require(
        scope.operation == "history_query",
        "only a bounded history request has a history delivery domain",
    )
    family_name, _channel_allowed = _READ_ROUTE_CLASS_FAMILIES[scope.route_class]
    channel_suffix = f"/{scope.channel}" if scope.channel else ""
    return (
        "ncp-history-domain/v1/"
        f"{scope.authority_realm_key[1]}/session/{scope.logical_session_id}/"
        f"{family_name}{channel_suffix}"
    )


@dataclass(frozen=True, slots=True)
class CanonicalObserverReadScope:
    authority_realm_key: tuple[str, str]
    source_session_kind: str
    logical_session_id: str
    source_generation: str
    operation: str
    route_class: str
    plane: str
    literal_route: str
    message_class: str
    channel: str
    extension: str
    declared_stream_digest: str
    schema_digest: str
    provider_contract_digest: str
    privacy_projection_digest: str
    authorization_audience: str
    history_clock_domain: str | None
    history_clock_incarnation: str | None
    history_window_start: int | None
    history_window_end: int | None
    scope_digest: str


def canonical_scope_digest(scope: CanonicalObserverReadScope) -> str:
    return _owned_json_domain_digest(
        "ncp.b01.bridge.CanonicalObserverReadScope@1",
        _registered_artifact_projection(
            scope,
            expected_type=CanonicalObserverReadScope,
            excluded_fields=frozenset({"scope_digest"}),
        ),
    )


def seal_scope(scope: CanonicalObserverReadScope) -> CanonicalObserverReadScope:
    return replace(scope, scope_digest=canonical_scope_digest(scope))


def validate_scope(scope: CanonicalObserverReadScope) -> None:
    _require(type(scope) is CanonicalObserverReadScope, "scope type is not exact")
    _require(
        type(scope.authority_realm_key) is tuple
        and len(scope.authority_realm_key) == 2,
        "scope authority realm is malformed",
    )
    for index, member in enumerate(scope.authority_realm_key):
        _authority_identifier(
            member,
            label=f"authority realm member {index}",
        )
    _closed_ascii(
        scope.source_session_kind,
        label="source session kind",
        maximum_bytes=32,
        identifier=True,
    )
    _require(
        scope.source_session_kind in SOURCE_SESSION_KINDS,
        "source session kind is outside the closed set",
    )
    _route_segment(scope.logical_session_id, label="logical session")
    _uuid4(scope.source_generation, label="source generation")
    _closed_ascii(
        scope.operation,
        label="read operation",
        maximum_bytes=32,
        identifier=True,
    )
    _closed_ascii(
        scope.route_class,
        label="route class",
        maximum_bytes=64,
        identifier=True,
    )
    _closed_ascii(scope.plane, label="plane", maximum_bytes=16, identifier=True)
    _closed_ascii(
        scope.literal_route,
        label="literal route",
        maximum_bytes=512,
    )
    _closed_ascii(
        scope.message_class,
        label="message class",
        maximum_bytes=64,
        identifier=True,
    )
    _route_segment(scope.channel, label="channel", allow_empty=True)
    _closed_ascii(
        scope.extension,
        label="extension",
        maximum_bytes=32,
        identifier=True,
    )
    _authority_identifier(
        scope.authorization_audience,
        label="authorization audience",
    )
    _require(
        scope.literal_route
        == canonical_read_route(
            realm=scope.authority_realm_key[1],
            logical_session_id=scope.logical_session_id,
            route_class=scope.route_class,
            channel=scope.channel,
        ),
        "literal route is not the exact route-factory result",
    )
    _require(scope.operation in READ_OPERATIONS, "scope operation is not read-only")
    expected_shape = READ_ROUTE_CLASS_SHAPES.get(scope.route_class)
    _require(
        expected_shape == (scope.plane, scope.message_class),
        "route class does not select its exact plane/message class",
    )
    _require(
        scope.extension == "none",
        "base Prisoma read scope cannot silently widen into an extension",
    )
    for value, label in (
        (scope.declared_stream_digest, "declared stream digest"),
        (scope.schema_digest, "schema digest"),
        (scope.provider_contract_digest, "provider contract digest"),
        (scope.privacy_projection_digest, "privacy projection digest"),
    ):
        _digest64(value, label=label, authority_bearing=True)
    if scope.operation == "subscribe":
        _require(
            scope.history_clock_domain is None
            and scope.history_clock_incarnation is None
            and scope.history_window_start is None
            and scope.history_window_end is None,
            "subscription scope cannot inherit history authority",
        )
    else:
        _authority_identifier(
            scope.history_clock_domain,
            label="history clock domain",
        )
        _uuid4(
            scope.history_clock_incarnation,
            label="history clock incarnation",
        )
        _require(
            type(scope.history_window_start) is int
            and type(scope.history_window_end) is int
            and 0
            <= scope.history_window_start
            < scope.history_window_end
            <= MAX_SAFE_INTEGER,
            "history scope lacks one exact bounded nonempty window",
        )
    _require(
        scope.scope_digest == canonical_scope_digest(scope),
        "scope digest does not bind the complete canonical scope",
    )


def canonical_history_request_digest(scope: CanonicalObserverReadScope) -> str:
    """Bind one bounded history request to its complete validated read scope."""

    validate_scope(scope)
    _require(
        scope.operation == "history_query",
        "only a bounded history scope has a history request digest",
    )
    return _owned_json_domain_digest(
        "ncp.b01.bridge.CanonicalBoundedHistoryRequest@1",
        {
            "canonical_scope_digest": scope.scope_digest,
            "history_clock_domain": scope.history_clock_domain,
            "history_clock_incarnation": scope.history_clock_incarnation,
            "history_window_end": scope.history_window_end,
            "history_window_start": scope.history_window_start,
        },
    )


@dataclass(frozen=True, slots=True)
class ObserverBoundaryReadScopeMembership:
    canonical_scope_digest: str
    boundary_principal: str
    boundary_instance: str
    delivery_domain_kind: str
    delivery_domain: str
    deadline_policy_id: str
    membership_digest: str


def boundary_membership_digest(
    membership: ObserverBoundaryReadScopeMembership,
) -> str:
    return _owned_json_domain_digest(
        "ncp.b01.bridge.ObserverBoundaryReadScopeMembership@1",
        _registered_artifact_projection(
            membership,
            expected_type=ObserverBoundaryReadScopeMembership,
            excluded_fields=frozenset({"membership_digest"}),
        ),
    )


def seal_boundary_membership(
    membership: ObserverBoundaryReadScopeMembership,
) -> ObserverBoundaryReadScopeMembership:
    return replace(
        membership,
        membership_digest=boundary_membership_digest(membership),
    )


def validate_boundary_membership(
    membership: ObserverBoundaryReadScopeMembership,
    *,
    scope: CanonicalObserverReadScope,
    expected_boundary_identity: tuple[str, str, str],
) -> None:
    validate_scope(scope)
    _require(
        type(membership) is ObserverBoundaryReadScopeMembership,
        "boundary membership type is not exact",
    )
    _require(
        type(expected_boundary_identity) is tuple
        and len(expected_boundary_identity) == 3,
        "expected boundary identity is malformed",
    )
    _authority_identifier(
        expected_boundary_identity[0],
        label="expected boundary principal",
    )
    _instance_identifier(
        expected_boundary_identity[1],
        label="expected boundary instance",
    )
    _authority_identifier(
        expected_boundary_identity[2],
        label="expected deadline policy",
    )
    _authority_identifier(
        membership.boundary_principal,
        label="boundary principal",
    )
    _instance_identifier(
        membership.boundary_instance,
        label="boundary instance",
    )
    _closed_ascii(
        membership.delivery_domain_kind,
        label="delivery domain kind",
        maximum_bytes=48,
        identifier=True,
    )
    _closed_ascii(
        membership.delivery_domain,
        label="delivery domain",
        maximum_bytes=512,
    )
    _authority_identifier(
        membership.deadline_policy_id,
        label="deadline policy",
    )
    expected_domain_kind = (
        LIVE_ROUTE_DOMAIN if scope.operation == "subscribe" else HISTORY_CONTENT_DOMAIN
    )
    expected_delivery_domain = (
        scope.literal_route
        if scope.operation == "subscribe"
        else canonical_history_delivery_domain(scope)
    )
    _require(
        membership.canonical_scope_digest == scope.scope_digest
        and (
            membership.boundary_principal,
            membership.boundary_instance,
            membership.deadline_policy_id,
        )
        == expected_boundary_identity
        and membership.delivery_domain_kind == expected_domain_kind
        and membership.delivery_domain == expected_delivery_domain
        and membership.membership_digest == boundary_membership_digest(membership),
        "boundary membership is not a bijective binding to the expected "
        "boundary, deadline policy, scope, and delivery domain",
    )


def _fixture_tag(
    domain: bytes,
    semantic_digest: str,
    *,
    fixture_key: bytes,
) -> str:
    _validate_fixture_key(fixture_key)
    return hmac.new(
        fixture_key,
        domain + b"\x00" + semantic_digest.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class SyntheticVerifiedAuthorizationIngressContext:
    provenance_kind: str
    observer_principal: str
    observer_instance: str
    authorization_audience: str
    endpoint_profile: str
    connection_instance: str
    replay_domain: str
    manifest_digest: str
    security_state_digest: str
    security_epoch: int
    revocation_epoch: int
    coordinator_clock_incarnation: str
    verified_at: int
    exclusive_not_after: int
    semantic_context_digest: str
    fixture_authentication_tag: str


def authorization_ingress_semantic_digest(
    context: SyntheticVerifiedAuthorizationIngressContext,
) -> str:
    return _owned_json_domain_digest(
        "ncp.b01.bridge.SyntheticVerifiedAuthorizationIngressContext@1",
        _registered_artifact_projection(
            context,
            expected_type=SyntheticVerifiedAuthorizationIngressContext,
            excluded_fields=frozenset(
                {"fixture_authentication_tag", "semantic_context_digest"}
            ),
        ),
    )


def seal_authorization_ingress_context(
    context: SyntheticVerifiedAuthorizationIngressContext,
    *,
    fixture_key: bytes,
) -> SyntheticVerifiedAuthorizationIngressContext:
    context = replace(
        context,
        semantic_context_digest=authorization_ingress_semantic_digest(context),
    )
    return replace(
        context,
        fixture_authentication_tag=_fixture_tag(
            b"NCP-B01-SYNTHETIC-AUTHORIZATION-INGRESS-CONTEXT-V1",
            context.semantic_context_digest,
            fixture_key=fixture_key,
        ),
    )


def authorization_ingress_artifact_digest(
    context: SyntheticVerifiedAuthorizationIngressContext,
) -> str:
    return _domain_digest(
        "ncp.b01.bridge.SyntheticVerifiedAuthorizationIngressArtifact@1",
        context,
    )


def validate_authorization_ingress_context(
    context: SyntheticVerifiedAuthorizationIngressContext,
    *,
    expected_observer_identity: tuple[str, str],
    expected_authorization_audience: str,
    expected_transport_context: tuple[str, str, str],
    expected_manifest_digest: str,
    expected_security_state: tuple[str, int, int],
    expected_coordinator_clock_incarnation: str,
    checked_at: int,
    fixture_key: bytes,
) -> None:
    _require(
        type(context) is SyntheticVerifiedAuthorizationIngressContext,
        "authorization ingress context type is not exact",
    )
    _require(
        type(expected_observer_identity) is tuple
        and len(expected_observer_identity) == 2,
        "expected observer identity is malformed",
    )
    _require(
        type(expected_security_state) is tuple
        and len(expected_security_state) == 3
        and type(expected_security_state[0]) is str
        and type(expected_security_state[1]) is int
        and type(expected_security_state[2]) is int
        and type(checked_at) is int,
        "expected authorization security cut or checked time is malformed",
    )
    _validate_expected_transport_context(
        expected_transport_context,
        label="expected authorization transport context",
    )
    for value, label in (
        (context.observer_principal, "authorization observer principal"),
        (context.authorization_audience, "authorization audience"),
        (context.replay_domain, "authorization ingress replay domain"),
    ):
        _authority_identifier(value, label=label)
    _instance_identifier(
        context.observer_instance,
        label="authorization observer instance",
    )
    _instance_identifier(
        context.connection_instance,
        label="authorization ingress connection",
    )
    _authority_identifier(
        expected_observer_identity[0],
        label="expected observer principal",
    )
    _instance_identifier(
        expected_observer_identity[1],
        label="expected observer instance",
    )
    _authority_identifier(
        expected_authorization_audience,
        label="expected authorization audience",
    )
    _closed_ascii(
        context.endpoint_profile,
        label="authorization endpoint profile",
        maximum_bytes=32,
        identifier=True,
    )
    _require(
        context.provenance_kind == "SYNTHETIC_VERIFIED_AUTHORIZATION_SERVER_INGRESS"
        and context.endpoint_profile == "production-secure",
        "authorization ingress provenance or endpoint profile is not closed",
    )
    _digest64(
        context.manifest_digest,
        label="authorization ingress manifest digest",
        authority_bearing=True,
    )
    _digest64(
        context.security_state_digest,
        label="authorization ingress security state digest",
        authority_bearing=True,
    )
    _digest64(
        expected_manifest_digest,
        label="expected authorization manifest digest",
        authority_bearing=True,
    )
    expected_security_digest, expected_security_epoch, expected_revocation_epoch = (
        expected_security_state
    )
    _digest64(
        expected_security_digest,
        label="expected security state digest",
        authority_bearing=True,
    )
    _uuid4(
        context.coordinator_clock_incarnation,
        label="authorization ingress coordinator clock",
    )
    _uuid4(
        expected_coordinator_clock_incarnation,
        label="expected authorization ingress coordinator clock",
    )
    _require(
        type(context.security_epoch) is int
        and 0 < context.security_epoch <= MAX_SAFE_INTEGER
        and type(context.revocation_epoch) is int
        and 0 < context.revocation_epoch <= MAX_SAFE_INTEGER
        and type(context.verified_at) is int
        and type(context.exclusive_not_after) is int
        and 0
        <= context.verified_at
        <= checked_at
        < context.exclusive_not_after
        <= MAX_SAFE_INTEGER,
        "authorization ingress epochs or deadline are invalid",
    )
    _require(
        0 < expected_security_epoch <= MAX_SAFE_INTEGER
        and 0 < expected_revocation_epoch <= MAX_SAFE_INTEGER,
        "expected authorization security epochs are invalid",
    )
    _require(
        (context.observer_principal, context.observer_instance)
        == expected_observer_identity
        and context.authorization_audience == expected_authorization_audience
        and (
            context.endpoint_profile,
            context.connection_instance,
            context.replay_domain,
        )
        == expected_transport_context
        and context.manifest_digest == expected_manifest_digest
        and context.coordinator_clock_incarnation
        == expected_coordinator_clock_incarnation
        and (
            context.security_state_digest,
            context.security_epoch,
            context.revocation_epoch,
        )
        == (
            expected_security_digest,
            expected_security_epoch,
            expected_revocation_epoch,
        ),
        "authorization ingress context is not the expected principal, "
        "audience, manifest, or security cut",
    )
    _require(
        context.semantic_context_digest
        == authorization_ingress_semantic_digest(context)
        and hmac.compare_digest(
            context.fixture_authentication_tag,
            _fixture_tag(
                b"NCP-B01-SYNTHETIC-AUTHORIZATION-INGRESS-CONTEXT-V1",
                context.semantic_context_digest,
                fixture_key=fixture_key,
            ),
        ),
        "authorization ingress context digest or fixture seal is invalid",
    )


@dataclass(frozen=True, slots=True)
class SyntheticVerifiedReleaseRecipientContext:
    provenance_kind: str
    boundary_principal: str
    boundary_instance: str
    recipient_principal: str
    recipient_instance: str
    connection_instance: str
    replay_domain: str
    endpoint_profile: str
    boundary_scope_membership_digest: str
    local_security_state_digest: str
    local_security_epoch: int
    local_revocation_epoch: int
    boundary_clock_incarnation: str
    verified_at: int
    exclusive_not_after: int
    semantic_context_digest: str
    fixture_authentication_tag: str


def release_recipient_semantic_digest(
    context: SyntheticVerifiedReleaseRecipientContext,
) -> str:
    return _owned_json_domain_digest(
        "ncp.b01.bridge.SyntheticVerifiedReleaseRecipientContext@1",
        _registered_artifact_projection(
            context,
            expected_type=SyntheticVerifiedReleaseRecipientContext,
            excluded_fields=frozenset(
                {"fixture_authentication_tag", "semantic_context_digest"}
            ),
        ),
    )


def seal_release_recipient_context(
    context: SyntheticVerifiedReleaseRecipientContext,
    *,
    fixture_key: bytes,
) -> SyntheticVerifiedReleaseRecipientContext:
    context = replace(
        context,
        semantic_context_digest=release_recipient_semantic_digest(context),
    )
    return replace(
        context,
        fixture_authentication_tag=_fixture_tag(
            b"NCP-B01-SYNTHETIC-RELEASE-RECIPIENT-CONTEXT-V1",
            context.semantic_context_digest,
            fixture_key=fixture_key,
        ),
    )


def release_recipient_artifact_digest(
    context: SyntheticVerifiedReleaseRecipientContext,
) -> str:
    return _domain_digest(
        "ncp.b01.bridge.SyntheticVerifiedReleaseRecipientArtifact@1",
        context,
    )


def validate_release_recipient_context(
    context: SyntheticVerifiedReleaseRecipientContext,
    *,
    membership: ObserverBoundaryReadScopeMembership,
    expected_recipient_identity: tuple[str, str],
    expected_transport_context: tuple[str, str, str],
    expected_local_security_state: tuple[str, int, int],
    expected_boundary_clock_incarnation: str,
    expected_context_artifact_digest: str,
    checked_at: int,
    fixture_key: bytes,
) -> None:
    _require(
        type(context) is SyntheticVerifiedReleaseRecipientContext,
        "release-recipient context type is not exact",
    )
    _require(
        type(expected_recipient_identity) is tuple
        and len(expected_recipient_identity) == 2,
        "expected release recipient identity is malformed",
    )
    _require(
        type(expected_local_security_state) is tuple
        and len(expected_local_security_state) == 3
        and type(expected_local_security_state[0]) is str
        and type(expected_local_security_state[1]) is int
        and type(expected_local_security_state[2]) is int
        and type(checked_at) is int,
        "expected release security cut or checked time is malformed",
    )
    _validate_expected_transport_context(
        expected_transport_context,
        label="expected release transport context",
    )
    _authority_identifier(
        expected_recipient_identity[0],
        label="expected release recipient principal",
    )
    _instance_identifier(
        expected_recipient_identity[1],
        label="expected release recipient instance",
    )
    for value, label in (
        (context.boundary_principal, "release boundary principal"),
        (context.recipient_principal, "release recipient principal"),
        (context.replay_domain, "release recipient replay domain"),
    ):
        _authority_identifier(value, label=label)
    for value, label in (
        (context.boundary_instance, "release boundary instance"),
        (context.recipient_instance, "release recipient instance"),
        (context.connection_instance, "release recipient connection"),
    ):
        _instance_identifier(value, label=label)
    _closed_ascii(
        context.endpoint_profile,
        label="release endpoint profile",
        maximum_bytes=32,
        identifier=True,
    )
    _require(
        context.provenance_kind == "SYNTHETIC_VERIFIED_BOUNDARY_LOCAL_RELEASE_RECIPIENT"
        and context.endpoint_profile == "production-secure",
        "release recipient provenance or endpoint profile is not closed",
    )
    _digest64(
        context.boundary_scope_membership_digest,
        label="release boundary membership digest",
        authority_bearing=True,
    )
    _digest64(
        context.local_security_state_digest,
        label="release local security state digest",
        authority_bearing=True,
    )
    expected_security_digest, expected_security_epoch, expected_revocation_epoch = (
        expected_local_security_state
    )
    _digest64(
        expected_security_digest,
        label="expected release security state digest",
        authority_bearing=True,
    )
    _digest64(
        expected_context_artifact_digest,
        label="expected release recipient context artifact digest",
        authority_bearing=True,
    )
    _uuid4(
        context.boundary_clock_incarnation,
        label="release recipient boundary clock",
    )
    _uuid4(
        expected_boundary_clock_incarnation,
        label="expected release recipient boundary clock",
    )
    _require(
        type(context.local_security_epoch) is int
        and 0 < context.local_security_epoch <= MAX_SAFE_INTEGER
        and type(context.local_revocation_epoch) is int
        and 0 < context.local_revocation_epoch <= MAX_SAFE_INTEGER
        and type(context.verified_at) is int
        and type(context.exclusive_not_after) is int
        and 0
        <= context.verified_at
        <= checked_at
        < context.exclusive_not_after
        <= MAX_SAFE_INTEGER,
        "release recipient epochs or deadline are invalid",
    )
    _require(
        0 < expected_security_epoch <= MAX_SAFE_INTEGER
        and 0 < expected_revocation_epoch <= MAX_SAFE_INTEGER,
        "expected release security epochs are invalid",
    )
    _require(
        (
            context.boundary_principal,
            context.boundary_instance,
            context.boundary_scope_membership_digest,
        )
        == (
            membership.boundary_principal,
            membership.boundary_instance,
            membership.membership_digest,
        )
        and context.boundary_clock_incarnation == expected_boundary_clock_incarnation
        and (context.recipient_principal, context.recipient_instance)
        == expected_recipient_identity
        and (
            context.endpoint_profile,
            context.connection_instance,
            context.replay_domain,
        )
        == expected_transport_context
        and (
            context.local_security_state_digest,
            context.local_security_epoch,
            context.local_revocation_epoch,
        )
        == (
            expected_security_digest,
            expected_security_epoch,
            expected_revocation_epoch,
        ),
        "release recipient context is not the expected boundary, recipient, "
        "membership, or local security cut",
    )
    _require(
        release_recipient_artifact_digest(context) == expected_context_artifact_digest
        and context.semantic_context_digest
        == release_recipient_semantic_digest(context)
        and hmac.compare_digest(
            context.fixture_authentication_tag,
            _fixture_tag(
                b"NCP-B01-SYNTHETIC-RELEASE-RECIPIENT-CONTEXT-V1",
                context.semantic_context_digest,
                fixture_key=fixture_key,
            ),
        ),
        "release recipient context digest or fixture seal is invalid",
    )


@dataclass(frozen=True, slots=True)
class ExpectedQualifiedDeadlineMappingStateCut:
    decision_artifact_digest: str
    source_clock_incarnation: str
    source_exclusive_not_after: int
    boundary_clock_incarnation: str
    coordinator_reference: int
    boundary_reference_lower: int
    source_applicability_start: int
    source_applicability_end: int
    target_applicability_start: int
    target_applicability_end: int
    minimum_rate_numerator: int
    minimum_rate_denominator: int
    rounding_rule: str
    correlation_authority: str
    qualification_digest: str
    source_receipt_digest: str
    source_receipt_authority: str
    source_receipt_current: bool
    mapping_policy_artifact_digest: str
    security_state_digest: str
    security_epoch: int
    revocation_epoch: int
    mapped_exclusive_not_after: int


def validate_expected_qualified_deadline_mapping_state_cut(
    cut: ExpectedQualifiedDeadlineMappingStateCut,
) -> None:
    _require(
        type(cut) is ExpectedQualifiedDeadlineMappingStateCut,
        "expected deadline mapping state cut type is not exact",
    )
    for value, label in (
        (cut.decision_artifact_digest, "expected mapped decision artifact"),
        (cut.qualification_digest, "expected mapping qualification"),
        (cut.source_receipt_digest, "expected mapping source receipt"),
        (cut.mapping_policy_artifact_digest, "expected mapping policy artifact"),
        (cut.security_state_digest, "expected mapping security state"),
    ):
        _digest64(value, label=label, authority_bearing=True)
    for value, label in (
        (cut.correlation_authority, "expected mapping correlation authority"),
        (cut.source_receipt_authority, "expected mapping receipt authority"),
    ):
        _authority_identifier(value, label=label)
    _uuid4(cut.source_clock_incarnation, label="expected mapping source clock")
    _uuid4(cut.boundary_clock_incarnation, label="expected mapping boundary clock")
    _closed_ascii(
        cut.rounding_rule,
        label="expected mapping rounding rule",
        maximum_bytes=32,
        identifier=True,
    )
    integer_fields = (
        cut.source_exclusive_not_after,
        cut.coordinator_reference,
        cut.boundary_reference_lower,
        cut.source_applicability_start,
        cut.source_applicability_end,
        cut.target_applicability_start,
        cut.target_applicability_end,
        cut.minimum_rate_numerator,
        cut.minimum_rate_denominator,
        cut.security_epoch,
        cut.revocation_epoch,
        cut.mapped_exclusive_not_after,
    )
    _require(
        all(
            type(value) is int and 0 <= value <= MAX_SAFE_INTEGER
            for value in integer_fields
        )
        and cut.minimum_rate_numerator > 0
        and cut.minimum_rate_denominator > 0
        and cut.security_epoch > 0
        and cut.revocation_epoch > 0
        and cut.rounding_rule == "LOWER_FLOOR"
        and cut.source_receipt_current is True
        and cut.source_receipt_authority == cut.correlation_authority
        and cut.source_applicability_start
        <= cut.coordinator_reference
        <= cut.source_exclusive_not_after
        <= cut.source_applicability_end
        and cut.target_applicability_start
        <= cut.boundary_reference_lower
        <= cut.mapped_exclusive_not_after
        <= cut.target_applicability_end,
        "expected deadline mapping cut is non-current, outside its horizon, "
        "or uses an invalid conservative mapping parameter",
    )


def expected_qualified_deadline_mapping_state_cut_digest(
    cut: ExpectedQualifiedDeadlineMappingStateCut,
) -> str:
    validate_expected_qualified_deadline_mapping_state_cut(cut)
    return _domain_digest(
        "ncp.b01.bridge.ExpectedQualifiedDeadlineMappingStateCut@1",
        cut,
    )


@dataclass(frozen=True, slots=True)
class QualifiedDecisionDeadlineMapping:
    provenance_kind: str
    decision_artifact_digest: str
    source_clock_incarnation: str
    source_exclusive_not_after: int
    boundary_clock_incarnation: str
    coordinator_reference: int
    boundary_reference_lower: int
    source_applicability_start: int
    source_applicability_end: int
    target_applicability_start: int
    target_applicability_end: int
    minimum_rate_numerator: int
    minimum_rate_denominator: int
    rounding_rule: str
    correlation_authority: str
    qualification_digest: str
    source_receipt_digest: str
    source_receipt_authority: str
    source_receipt_current: bool
    mapping_policy_artifact_digest: str
    security_state_digest: str
    security_epoch: int
    revocation_epoch: int
    mapped_exclusive_not_after: int
    semantic_mapping_digest: str
    fixture_authentication_tag: str


def qualified_deadline_mapping_semantic_digest(
    mapping: QualifiedDecisionDeadlineMapping,
) -> str:
    return _owned_json_domain_digest(
        "ncp.b01.bridge.QualifiedDecisionDeadlineMapping@1",
        _registered_artifact_projection(
            mapping,
            expected_type=QualifiedDecisionDeadlineMapping,
            excluded_fields=frozenset(
                {"fixture_authentication_tag", "semantic_mapping_digest"}
            ),
        ),
    )


def seal_qualified_deadline_mapping(
    mapping: QualifiedDecisionDeadlineMapping,
    *,
    fixture_key: bytes,
) -> QualifiedDecisionDeadlineMapping:
    mapping = replace(
        mapping,
        semantic_mapping_digest=qualified_deadline_mapping_semantic_digest(mapping),
    )
    return replace(
        mapping,
        fixture_authentication_tag=_fixture_tag(
            b"NCP-B01-SYNTHETIC-QUALIFIED-DEADLINE-MAPPING-V1",
            mapping.semantic_mapping_digest,
            fixture_key=fixture_key,
        ),
    )


def qualified_deadline_mapping_artifact_digest(
    mapping: QualifiedDecisionDeadlineMapping,
) -> str:
    return _domain_digest(
        "ncp.b01.bridge.QualifiedDecisionDeadlineMappingArtifact@1",
        mapping,
    )


def validate_qualified_deadline_mapping(
    mapping: QualifiedDecisionDeadlineMapping,
    *,
    decision: SealedObserverReadAuthorizationDecision,
    expected_state_cut: ExpectedQualifiedDeadlineMappingStateCut,
    expected_boundary_clock_incarnation: str,
    expected_mapping_policy_artifact_digest: str,
    expected_security_state: tuple[str, int, int],
    fixture_key: bytes,
) -> None:
    _require(
        type(mapping) is QualifiedDecisionDeadlineMapping,
        "qualified decision deadline mapping type is not exact",
    )
    validate_expected_qualified_deadline_mapping_state_cut(expected_state_cut)
    expected_state_projection = _registered_artifact_projection(
        expected_state_cut,
        expected_type=ExpectedQualifiedDeadlineMappingStateCut,
    )
    _require(
        all(
            object.__getattribute__(mapping, name) == expected_value
            for name, expected_value in expected_state_projection.items()
        ),
        "qualified deadline mapping differs from its independently supplied "
        "authority, receipt, policy, clock, rate, horizon, or security cut",
    )
    _uuid4(
        mapping.source_clock_incarnation,
        label="deadline mapping source clock",
    )
    _uuid4(
        mapping.boundary_clock_incarnation,
        label="deadline mapping boundary clock",
    )
    _uuid4(
        expected_boundary_clock_incarnation,
        label="expected deadline mapping boundary clock",
    )
    for value, label in (
        (mapping.correlation_authority, "deadline mapping authority"),
        (mapping.source_receipt_authority, "deadline mapping receipt authority"),
    ):
        _authority_identifier(value, label=label)
    _closed_ascii(
        mapping.rounding_rule,
        label="deadline mapping rounding rule",
        maximum_bytes=32,
        identifier=True,
    )
    for value, label in (
        (mapping.decision_artifact_digest, "mapped decision artifact digest"),
        (mapping.qualification_digest, "deadline mapping qualification digest"),
        (mapping.source_receipt_digest, "deadline mapping receipt digest"),
        (
            mapping.mapping_policy_artifact_digest,
            "deadline mapping policy artifact digest",
        ),
        (mapping.security_state_digest, "deadline mapping security state digest"),
        (mapping.semantic_mapping_digest, "semantic deadline mapping digest"),
        (
            mapping.fixture_authentication_tag,
            "deadline mapping fixture authentication tag",
        ),
        (
            expected_mapping_policy_artifact_digest,
            "expected deadline mapping policy artifact digest",
        ),
    ):
        _digest64(value, label=label, authority_bearing=True)
    _require(
        type(expected_security_state) is tuple
        and len(expected_security_state) == 3
        and type(expected_security_state[0]) is str
        and type(expected_security_state[1]) is int
        and type(expected_security_state[2]) is int,
        "expected deadline mapping security cut is malformed",
    )
    expected_security_digest, expected_security_epoch, expected_revocation_epoch = (
        expected_security_state
    )
    _digest64(
        expected_security_digest,
        label="expected deadline mapping security state digest",
        authority_bearing=True,
    )
    integer_fields = (
        mapping.source_exclusive_not_after,
        mapping.coordinator_reference,
        mapping.boundary_reference_lower,
        mapping.source_applicability_start,
        mapping.source_applicability_end,
        mapping.target_applicability_start,
        mapping.target_applicability_end,
        mapping.minimum_rate_numerator,
        mapping.minimum_rate_denominator,
        mapping.security_epoch,
        mapping.revocation_epoch,
        mapping.mapped_exclusive_not_after,
    )
    _require(
        all(
            type(value) is int and 0 <= value <= MAX_SAFE_INTEGER
            for value in integer_fields
        )
        and mapping.minimum_rate_numerator > 0
        and mapping.minimum_rate_denominator > 0
        and mapping.security_epoch > 0
        and mapping.revocation_epoch > 0,
        "deadline mapping integer or epoch is outside the portable safe range",
    )
    _require(
        mapping.provenance_kind == "SYNTHETIC_AUTHENTICATED_CONSERVATIVE_CLOCK_MAPPING"
        and mapping.rounding_rule == "LOWER_FLOOR"
        and mapping.source_receipt_current is True
        and mapping.source_receipt_authority == mapping.correlation_authority
        and mapping.source_clock_incarnation == decision.coordinator_clock_incarnation
        and mapping.source_exclusive_not_after == decision.exclusive_not_after
        and mapping.boundary_clock_incarnation
        == expected_boundary_clock_incarnation
        == expected_state_cut.boundary_clock_incarnation
        and mapping.mapping_policy_artifact_digest
        == expected_mapping_policy_artifact_digest
        == expected_state_cut.mapping_policy_artifact_digest
        and (
            mapping.security_state_digest,
            mapping.security_epoch,
            mapping.revocation_epoch,
        )
        == (
            expected_security_digest,
            expected_security_epoch,
            expected_revocation_epoch,
        )
        == (
            expected_state_cut.security_state_digest,
            expected_state_cut.security_epoch,
            expected_state_cut.revocation_epoch,
        )
        and mapping.source_applicability_start
        <= mapping.coordinator_reference
        <= mapping.source_exclusive_not_after
        <= mapping.source_applicability_end
        and mapping.target_applicability_start
        <= mapping.boundary_reference_lower
        <= mapping.mapped_exclusive_not_after
        <= mapping.target_applicability_end,
        "deadline mapping does not bind the exact decision, clock, mapping "
        "policy, receipt currentness, security cut, or applicability horizon",
    )
    delta = mapping.source_exclusive_not_after - mapping.coordinator_reference
    _require(
        delta == 0 or mapping.minimum_rate_numerator <= MAX_SAFE_INTEGER // delta,
        "deadline mapping multiplication exceeds the portable safe range",
    )
    expected_advance = (
        delta * mapping.minimum_rate_numerator
    ) // mapping.minimum_rate_denominator
    _require(
        expected_advance <= MAX_SAFE_INTEGER
        and mapping.boundary_reference_lower <= MAX_SAFE_INTEGER - expected_advance
        and mapping.mapped_exclusive_not_after
        == mapping.boundary_reference_lower + expected_advance,
        "deadline mapping is not the conservative lower image",
    )
    _require(
        mapping.decision_artifact_digest == read_decision_artifact_digest(decision)
        and mapping.semantic_mapping_digest
        == qualified_deadline_mapping_semantic_digest(mapping)
        and hmac.compare_digest(
            mapping.fixture_authentication_tag,
            _fixture_tag(
                b"NCP-B01-SYNTHETIC-QUALIFIED-DEADLINE-MAPPING-V1",
                mapping.semantic_mapping_digest,
                fixture_key=fixture_key,
            ),
        ),
        "deadline mapping decision binding, semantic digest, or fixture seal "
        "is invalid",
    )


@dataclass(frozen=True, slots=True)
class SyntheticAuthenticatedGrantCurrentnessEvidence:
    provenance_kind: str
    boundary_principal: str
    boundary_instance: str
    boundary_clock_incarnation: str
    observer_principal: str
    observer_instance: str
    canonical_scope_digest: str
    boundary_scope_membership_digest: str
    read_decision_artifact_digest: str
    capability_digest: str
    grant_digest: str
    grant_currentness_receipt_digest: str
    boundary_state_head_digest: str
    grant_entry_head_digest: str
    release_counter_state_digest: str
    state_version: int
    prior_release_count: int
    local_grant_exclusive_not_after: int
    verified_at: int
    exclusive_not_after: int
    security_state_digest: str
    security_epoch: int
    revocation_epoch: int
    current: bool
    semantic_evidence_digest: str
    fixture_authentication_tag: str


@dataclass(frozen=True, slots=True)
class ExpectedGrantCurrentnessStateCut:
    boundary_state_head_digest: str
    grant_entry_head_digest: str
    state_version: int
    prior_release_count: int
    grant_currentness_receipt_digest: str
    local_grant_exclusive_not_after: int
    evidence_artifact_digest: str


def validate_expected_grant_currentness_state_cut(
    cut: ExpectedGrantCurrentnessStateCut,
) -> None:
    _require(
        type(cut) is ExpectedGrantCurrentnessStateCut,
        "expected grant currentness state cut type is not exact",
    )
    for value, label in (
        (cut.boundary_state_head_digest, "expected boundary state head"),
        (cut.grant_entry_head_digest, "expected grant entry head"),
        (
            cut.grant_currentness_receipt_digest,
            "expected grant currentness receipt",
        ),
        (
            cut.evidence_artifact_digest,
            "expected grant currentness evidence artifact",
        ),
    ):
        _digest64(value, label=label, authority_bearing=True)
    _require(
        type(cut.state_version) is int
        and 1 <= cut.state_version <= MAX_SAFE_INTEGER
        and type(cut.prior_release_count) is int
        and 0 <= cut.prior_release_count <= MAX_SAFE_INTEGER
        and type(cut.local_grant_exclusive_not_after) is int
        and 0 < cut.local_grant_exclusive_not_after <= MAX_SAFE_INTEGER,
        "expected grant currentness version, count, or deadline is invalid",
    )


def grant_release_counter_state_digest(
    evidence: SyntheticAuthenticatedGrantCurrentnessEvidence,
) -> str:
    """Return the exact pre-release quota state represented by evidence."""

    return _owned_json_domain_digest(
        "ncp.b01.bridge.ObserverReadReleaseCounterState@1",
        {
            "boundary_instance": evidence.boundary_instance,
            "boundary_principal": evidence.boundary_principal,
            "boundary_scope_membership_digest": (
                evidence.boundary_scope_membership_digest
            ),
            "boundary_state_head_digest": evidence.boundary_state_head_digest,
            "grant_entry_head_digest": evidence.grant_entry_head_digest,
            "observer_instance": evidence.observer_instance,
            "observer_principal": evidence.observer_principal,
            "prior_release_count": evidence.prior_release_count,
            "read_decision_artifact_digest": (evidence.read_decision_artifact_digest),
            "state_version": evidence.state_version,
        },
    )


def next_grant_release_counter_state_digest(
    *,
    evidence: SyntheticAuthenticatedGrantCurrentnessEvidence,
    release_idempotency_key: str,
    release_ordinal: int,
) -> str:
    """Return the successor quota-head identity selected by one release CAS."""

    _uuid4(release_idempotency_key, label="release counter idempotency key")
    _require(
        type(release_ordinal) is int and 1 <= release_ordinal <= MAX_SAFE_INTEGER,
        "release counter ordinal is invalid",
    )
    return _owned_json_domain_digest(
        "ncp.b01.bridge.ObserverReadReleaseCounterSuccessor@1",
        {
            "prior_release_counter_state_digest": (
                evidence.release_counter_state_digest
            ),
            "read_decision_artifact_digest": (evidence.read_decision_artifact_digest),
            "release_idempotency_key": release_idempotency_key,
            "release_ordinal": release_ordinal,
        },
    )


def grant_currentness_semantic_digest(
    evidence: SyntheticAuthenticatedGrantCurrentnessEvidence,
) -> str:
    return _owned_json_domain_digest(
        "ncp.b01.bridge.SyntheticAuthenticatedGrantCurrentnessEvidence@1",
        _registered_artifact_projection(
            evidence,
            expected_type=SyntheticAuthenticatedGrantCurrentnessEvidence,
            excluded_fields=frozenset(
                {"fixture_authentication_tag", "semantic_evidence_digest"}
            ),
        ),
    )


def seal_grant_currentness_evidence(
    evidence: SyntheticAuthenticatedGrantCurrentnessEvidence,
    *,
    fixture_key: bytes,
) -> SyntheticAuthenticatedGrantCurrentnessEvidence:
    evidence = replace(
        evidence,
        release_counter_state_digest=grant_release_counter_state_digest(evidence),
    )
    evidence = replace(
        evidence,
        semantic_evidence_digest=grant_currentness_semantic_digest(evidence),
    )
    return replace(
        evidence,
        fixture_authentication_tag=_fixture_tag(
            b"NCP-B01-SYNTHETIC-GRANT-CURRENTNESS-EVIDENCE-V1",
            evidence.semantic_evidence_digest,
            fixture_key=fixture_key,
        ),
    )


def grant_currentness_artifact_digest(
    evidence: SyntheticAuthenticatedGrantCurrentnessEvidence,
) -> str:
    return _domain_digest(
        "ncp.b01.bridge.SyntheticAuthenticatedGrantCurrentnessArtifact@1",
        evidence,
    )


def validate_grant_currentness_evidence(
    evidence: SyntheticAuthenticatedGrantCurrentnessEvidence,
    *,
    scope: CanonicalObserverReadScope,
    membership: ObserverBoundaryReadScopeMembership,
    decision: SealedObserverReadAuthorizationDecision,
    expected_observer_identity: tuple[str, str],
    expected_boundary_identity: tuple[str, str, str],
    expected_boundary_clock_incarnation: str,
    expected_security_state: tuple[str, int, int],
    expected_state_cut: ExpectedGrantCurrentnessStateCut,
    checked_at: int,
    fixture_key: bytes,
) -> None:
    _require(
        type(evidence) is SyntheticAuthenticatedGrantCurrentnessEvidence,
        "grant currentness evidence type is not exact",
    )
    validate_scope(scope)
    validate_boundary_membership(
        membership,
        scope=scope,
        expected_boundary_identity=expected_boundary_identity,
    )
    _require(
        type(decision) is SealedObserverReadAuthorizationDecision,
        "grant currentness decision type is not exact",
    )
    validate_expected_grant_currentness_state_cut(expected_state_cut)
    _require(
        type(expected_observer_identity) is tuple
        and len(expected_observer_identity) == 2,
        "expected grant currentness observer identity is malformed",
    )
    _authority_identifier(
        expected_observer_identity[0],
        label="expected grant currentness observer principal",
    )
    _instance_identifier(
        expected_observer_identity[1],
        label="expected grant currentness observer instance",
    )
    _authority_identifier(
        evidence.boundary_principal,
        label="grant currentness boundary principal",
    )
    _instance_identifier(
        evidence.boundary_instance,
        label="grant currentness boundary instance",
    )
    _authority_identifier(
        evidence.observer_principal,
        label="grant currentness observer principal",
    )
    _instance_identifier(
        evidence.observer_instance,
        label="grant currentness observer instance",
    )
    _uuid4(
        evidence.boundary_clock_incarnation,
        label="grant currentness boundary clock",
    )
    _uuid4(
        expected_boundary_clock_incarnation,
        label="expected grant currentness boundary clock",
    )
    for value, label in (
        (evidence.canonical_scope_digest, "grant currentness scope digest"),
        (
            evidence.boundary_scope_membership_digest,
            "grant currentness membership digest",
        ),
        (
            evidence.read_decision_artifact_digest,
            "grant currentness decision artifact digest",
        ),
        (evidence.capability_digest, "grant currentness capability digest"),
        (evidence.grant_digest, "grant currentness grant digest"),
        (
            evidence.grant_currentness_receipt_digest,
            "grant currentness receipt digest",
        ),
        (
            evidence.boundary_state_head_digest,
            "grant currentness boundary state head",
        ),
        (evidence.grant_entry_head_digest, "grant currentness entry head"),
        (
            evidence.release_counter_state_digest,
            "grant currentness release counter state",
        ),
        (evidence.security_state_digest, "grant currentness security state"),
        (
            evidence.semantic_evidence_digest,
            "grant currentness semantic evidence digest",
        ),
        (
            evidence.fixture_authentication_tag,
            "grant currentness fixture authentication tag",
        ),
    ):
        _digest64(value, label=label, authority_bearing=True)
    _require(
        type(expected_security_state) is tuple
        and len(expected_security_state) == 3
        and all(type(value) is int for value in expected_security_state[1:])
        and type(expected_security_state[0]) is str,
        "expected grant currentness security cut is malformed",
    )
    (
        expected_security_digest,
        expected_security_epoch,
        expected_revocation_epoch,
    ) = expected_security_state
    _digest64(
        expected_security_digest,
        label="expected grant currentness security state",
        authority_bearing=True,
    )
    integer_fields = (
        evidence.state_version,
        evidence.prior_release_count,
        evidence.local_grant_exclusive_not_after,
        evidence.verified_at,
        evidence.exclusive_not_after,
        evidence.security_epoch,
        evidence.revocation_epoch,
        checked_at,
        expected_security_epoch,
        expected_revocation_epoch,
    )
    _require(
        all(
            type(value) is int and 0 <= value <= MAX_SAFE_INTEGER
            for value in integer_fields
        )
        and evidence.state_version > 0
        and evidence.security_epoch > 0
        and evidence.revocation_epoch > 0
        and expected_security_epoch > 0
        and expected_revocation_epoch > 0,
        "grant currentness integer, epoch, or time is invalid",
    )
    _require(
        evidence.provenance_kind == "SYNTHETIC_AUTHENTICATED_BOUNDARY_GRANT_CURRENTNESS"
        and evidence.current is True
        and (
            evidence.boundary_principal,
            evidence.boundary_instance,
        )
        == (
            membership.boundary_principal,
            membership.boundary_instance,
        )
        and evidence.boundary_clock_incarnation == expected_boundary_clock_incarnation
        and (evidence.observer_principal, evidence.observer_instance)
        == expected_observer_identity
        and evidence.canonical_scope_digest == scope.scope_digest
        and evidence.boundary_scope_membership_digest == membership.membership_digest
        and evidence.read_decision_artifact_digest
        == read_decision_artifact_digest(decision)
        and evidence.capability_digest == decision.capability_digest
        and evidence.grant_digest == decision.grant_digest
        and evidence.grant_currentness_receipt_digest
        == expected_state_cut.grant_currentness_receipt_digest
        and evidence.boundary_state_head_digest
        == expected_state_cut.boundary_state_head_digest
        and evidence.grant_entry_head_digest
        == expected_state_cut.grant_entry_head_digest
        and evidence.state_version == expected_state_cut.state_version
        and evidence.prior_release_count == expected_state_cut.prior_release_count
        and evidence.local_grant_exclusive_not_after
        == expected_state_cut.local_grant_exclusive_not_after
        and (
            evidence.security_state_digest,
            evidence.security_epoch,
            evidence.revocation_epoch,
        )
        == (
            expected_security_digest,
            expected_security_epoch,
            expected_revocation_epoch,
        )
        and evidence.release_counter_state_digest
        == grant_release_counter_state_digest(evidence)
        and 0
        <= evidence.verified_at
        <= checked_at
        < evidence.exclusive_not_after
        <= evidence.local_grant_exclusive_not_after
        <= MAX_SAFE_INTEGER,
        "grant currentness evidence is not the exact live state, quota head, "
        "clock incarnation, grant deadline, or security cut",
    )
    _require(
        grant_currentness_artifact_digest(evidence)
        == expected_state_cut.evidence_artifact_digest
        and evidence.semantic_evidence_digest
        == grant_currentness_semantic_digest(evidence)
        and hmac.compare_digest(
            evidence.fixture_authentication_tag,
            _fixture_tag(
                b"NCP-B01-SYNTHETIC-GRANT-CURRENTNESS-EVIDENCE-V1",
                evidence.semantic_evidence_digest,
                fixture_key=fixture_key,
            ),
        ),
        "grant currentness evidence digest or fixture seal is invalid",
    )


@dataclass(frozen=True, slots=True)
class ObserverReadReleaseCAS:
    observer_principal: str
    observer_instance: str
    source_session_kind: str
    logical_session_id: str
    source_generation: str
    canonical_scope_digest: str
    boundary_scope_membership_digest: str
    caller_operation_id: str
    caller_request_digest: str
    release_idempotency_key: str
    authorization_ingress_artifact_digest: str
    release_recipient_context_artifact_digest: str
    read_decision_artifact_digest: str
    capability_digest: str
    grant_digest: str
    grant_currentness_evidence_artifact_digest: str
    boundary_clock_incarnation: str
    prior_release_count: int
    release_ordinal: int
    prior_release_counter_state_digest: str
    next_release_counter_state_digest: str
    local_grant_not_after: int
    grant_currentness_not_after: int
    qualified_deadline_mapping_artifact_digest: str
    mapped_decision_not_after: int
    local_release_context_not_after: int
    effective_release_not_after: int
    cas_digest: str


def release_cas_digest(cas: ObserverReadReleaseCAS) -> str:
    return _owned_json_domain_digest(
        "ncp.b01.bridge.ObserverReadReleaseCAS@1",
        _registered_artifact_projection(
            cas,
            expected_type=ObserverReadReleaseCAS,
            excluded_fields=frozenset({"cas_digest"}),
        ),
    )


def seal_release_cas(cas: ObserverReadReleaseCAS) -> ObserverReadReleaseCAS:
    return replace(cas, cas_digest=release_cas_digest(cas))


def validate_release_cas(
    cas: ObserverReadReleaseCAS,
    *,
    scope: CanonicalObserverReadScope,
    membership: ObserverBoundaryReadScopeMembership,
    decision: SealedObserverReadAuthorizationDecision,
    release_context: SyntheticVerifiedReleaseRecipientContext,
    qualified_deadline_mapping: QualifiedDecisionDeadlineMapping,
    grant_currentness_evidence: SyntheticAuthenticatedGrantCurrentnessEvidence,
    expected_observer_identity: tuple[str, str],
    expected_boundary_identity: tuple[str, str, str],
    expected_authorization_audience: str,
    expected_authorization_cut: ExpectedObserverReadAuthorizationCut,
    expected_issuer_identity: tuple[str, str, str],
    expected_release_recipient_identity: tuple[str, str],
    expected_release_transport_context: tuple[str, str, str],
    expected_local_security_state: tuple[str, int, int],
    expected_release_context_artifact_digest: str,
    expected_grant_currentness_state_cut: ExpectedGrantCurrentnessStateCut,
    expected_deadline_mapping_state_cut: ExpectedQualifiedDeadlineMappingStateCut,
    release_idempotency_key: str,
    expected_boundary_clock_incarnation: str,
    expected_mapping_policy_artifact_digest: str,
    checked_at: int,
    fixture_key: bytes,
) -> None:
    _require(type(cas) is ObserverReadReleaseCAS, "release CAS type is not exact")
    validate_scope(scope)
    validate_boundary_membership(
        membership,
        scope=scope,
        expected_boundary_identity=expected_boundary_identity,
    )
    validate_read_decision(
        decision,
        scope=scope,
        membership=membership,
        expected_boundary_identity=expected_boundary_identity,
        expected_observer_identity=expected_observer_identity,
        expected_authorization_audience=expected_authorization_audience,
        expected_authorization_cut=expected_authorization_cut,
        expected_issuer_identity=expected_issuer_identity,
        fixture_key=fixture_key,
    )
    validate_release_recipient_context(
        release_context,
        membership=membership,
        expected_recipient_identity=expected_release_recipient_identity,
        expected_transport_context=expected_release_transport_context,
        expected_local_security_state=expected_local_security_state,
        expected_boundary_clock_incarnation=(expected_boundary_clock_incarnation),
        expected_context_artifact_digest=(expected_release_context_artifact_digest),
        checked_at=checked_at,
        fixture_key=fixture_key,
    )
    validate_qualified_deadline_mapping(
        qualified_deadline_mapping,
        decision=decision,
        expected_state_cut=expected_deadline_mapping_state_cut,
        expected_boundary_clock_incarnation=(expected_boundary_clock_incarnation),
        expected_mapping_policy_artifact_digest=(
            expected_mapping_policy_artifact_digest
        ),
        expected_security_state=expected_local_security_state,
        fixture_key=fixture_key,
    )
    validate_grant_currentness_evidence(
        grant_currentness_evidence,
        scope=scope,
        membership=membership,
        decision=decision,
        expected_observer_identity=expected_observer_identity,
        expected_boundary_identity=expected_boundary_identity,
        expected_boundary_clock_incarnation=(expected_boundary_clock_incarnation),
        expected_security_state=expected_local_security_state,
        expected_state_cut=expected_grant_currentness_state_cut,
        checked_at=checked_at,
        fixture_key=fixture_key,
    )
    _authority_identifier(cas.observer_principal, label="release CAS observer")
    _instance_identifier(
        cas.observer_instance,
        label="release CAS observer instance",
    )
    _uuid4(
        cas.boundary_clock_incarnation,
        label="release CAS boundary clock",
    )
    _uuid4(cas.caller_operation_id, label="release CAS caller operation")
    _uuid4(cas.release_idempotency_key, label="release CAS idempotency key")
    for value, label in (
        (cas.canonical_scope_digest, "release CAS scope digest"),
        (cas.boundary_scope_membership_digest, "release CAS membership digest"),
        (cas.caller_request_digest, "release CAS caller request digest"),
        (
            cas.authorization_ingress_artifact_digest,
            "release CAS authorization ingress artifact digest",
        ),
        (
            cas.release_recipient_context_artifact_digest,
            "release CAS recipient context artifact digest",
        ),
        (cas.read_decision_artifact_digest, "release CAS decision artifact digest"),
        (cas.capability_digest, "release CAS capability digest"),
        (cas.grant_digest, "release CAS grant digest"),
        (
            cas.grant_currentness_evidence_artifact_digest,
            "release CAS grant currentness evidence artifact digest",
        ),
        (
            cas.prior_release_counter_state_digest,
            "release CAS prior release counter state digest",
        ),
        (
            cas.next_release_counter_state_digest,
            "release CAS next release counter state digest",
        ),
        (
            cas.qualified_deadline_mapping_artifact_digest,
            "release CAS qualified deadline mapping artifact digest",
        ),
        (cas.cas_digest, "release CAS digest"),
    ):
        _digest64(value, label=label, authority_bearing=True)
    mapped_decision_not_after = qualified_deadline_mapping.mapped_exclusive_not_after
    integer_fields = (
        cas.prior_release_count,
        cas.release_ordinal,
        cas.local_grant_not_after,
        cas.grant_currentness_not_after,
        cas.mapped_decision_not_after,
        cas.local_release_context_not_after,
        cas.effective_release_not_after,
        checked_at,
    )
    _require(
        all(
            type(value) is int and 0 <= value <= MAX_SAFE_INTEGER
            for value in integer_fields
        )
        and 0
        <= checked_at
        < min(
            grant_currentness_evidence.local_grant_exclusive_not_after,
            grant_currentness_evidence.exclusive_not_after,
            mapped_decision_not_after,
            release_context.exclusive_not_after,
        )
        <= MAX_SAFE_INTEGER,
        "release CAS deadline inputs are invalid or expired",
    )
    expected_effective_deadline = min(
        grant_currentness_evidence.local_grant_exclusive_not_after,
        grant_currentness_evidence.exclusive_not_after,
        mapped_decision_not_after,
        release_context.exclusive_not_after,
    )
    expected_release_ordinal = grant_currentness_evidence.prior_release_count + 1
    expected_next_counter_state_digest = next_grant_release_counter_state_digest(
        evidence=grant_currentness_evidence,
        release_idempotency_key=release_idempotency_key,
        release_ordinal=expected_release_ordinal,
    )
    _require(
        (cas.observer_principal, cas.observer_instance) == expected_observer_identity
        and (
            cas.source_session_kind,
            cas.logical_session_id,
            cas.source_generation,
        )
        == (
            scope.source_session_kind,
            scope.logical_session_id,
            scope.source_generation,
        )
        and cas.canonical_scope_digest == scope.scope_digest
        and cas.boundary_scope_membership_digest == membership.membership_digest
        and cas.caller_operation_id == decision.caller_operation_id
        and cas.caller_request_digest == decision.caller_request_digest
        and cas.release_idempotency_key == release_idempotency_key
        and cas.authorization_ingress_artifact_digest
        == authorization_ingress_artifact_digest(decision.authorization_ingress_context)
        and cas.release_recipient_context_artifact_digest
        == release_recipient_artifact_digest(release_context)
        and cas.read_decision_artifact_digest == read_decision_artifact_digest(decision)
        and cas.capability_digest == decision.capability_digest
        and cas.grant_digest == decision.grant_digest
        and cas.grant_currentness_evidence_artifact_digest
        == grant_currentness_artifact_digest(grant_currentness_evidence)
        and cas.boundary_clock_incarnation
        == expected_boundary_clock_incarnation
        == release_context.boundary_clock_incarnation
        == qualified_deadline_mapping.boundary_clock_incarnation
        == grant_currentness_evidence.boundary_clock_incarnation
        and cas.prior_release_count
        == grant_currentness_evidence.prior_release_count
        == expected_grant_currentness_state_cut.prior_release_count
        and cas.release_ordinal == expected_release_ordinal
        and cas.release_ordinal <= decision.maximum_release_count
        and cas.prior_release_counter_state_digest
        == grant_currentness_evidence.release_counter_state_digest
        and cas.next_release_counter_state_digest == expected_next_counter_state_digest
        and cas.local_grant_not_after
        == grant_currentness_evidence.local_grant_exclusive_not_after
        and cas.grant_currentness_not_after
        == grant_currentness_evidence.exclusive_not_after
        and cas.qualified_deadline_mapping_artifact_digest
        == qualified_deadline_mapping_artifact_digest(qualified_deadline_mapping)
        and cas.mapped_decision_not_after == mapped_decision_not_after
        and cas.local_release_context_not_after == release_context.exclusive_not_after
        and cas.effective_release_not_after == expected_effective_deadline
        and cas.cas_digest == release_cas_digest(cas),
        "release CAS does not bind one observer, session, scope, operation, "
        "idempotency key, provenance pair, or minimum deadline",
    )


def expected_authorization_cut_digest(
    cut: ExpectedObserverReadAuthorizationCut,
) -> str:
    validate_expected_authorization_cut(cut)
    return _domain_digest(
        "ncp.b01.bridge.ExpectedObserverReadAuthorizationCut@1",
        cut,
    )


def expected_grant_currentness_state_cut_digest(
    cut: ExpectedGrantCurrentnessStateCut,
) -> str:
    validate_expected_grant_currentness_state_cut(cut)
    return _domain_digest(
        "ncp.b01.bridge.ExpectedGrantCurrentnessStateCut@1",
        cut,
    )


@dataclass(frozen=True, slots=True)
class SyntheticValidatedObserverReadReleaseCASReceipt:
    provenance_kind: str
    validation_event_id: str
    validator_principal: str
    validator_instance: str
    boundary_clock_incarnation: str
    release_cas_artifact_digest: str
    authorization_ingress_artifact_digest: str
    release_recipient_context_artifact_digest: str
    read_decision_artifact_digest: str
    qualified_deadline_mapping_artifact_digest: str
    grant_currentness_evidence_artifact_digest: str
    expected_authorization_cut_digest: str
    expected_grant_currentness_state_cut_digest: str
    expected_deadline_mapping_state_cut_digest: str
    checked_at: int
    effective_release_not_after: int
    semantic_receipt_digest: str
    fixture_authentication_tag: str


def validated_release_cas_receipt_semantic_digest(
    receipt: SyntheticValidatedObserverReadReleaseCASReceipt,
) -> str:
    return _owned_json_domain_digest(
        "ncp.b01.bridge.SyntheticValidatedObserverReadReleaseCASReceipt@1",
        _registered_artifact_projection(
            receipt,
            expected_type=SyntheticValidatedObserverReadReleaseCASReceipt,
            excluded_fields=frozenset(
                {"fixture_authentication_tag", "semantic_receipt_digest"}
            ),
        ),
    )


def _seal_validated_release_cas_receipt(
    receipt: SyntheticValidatedObserverReadReleaseCASReceipt,
    *,
    fixture_key: bytes,
) -> SyntheticValidatedObserverReadReleaseCASReceipt:
    receipt = replace(
        receipt,
        semantic_receipt_digest=(
            validated_release_cas_receipt_semantic_digest(receipt)
        ),
    )
    return replace(
        receipt,
        fixture_authentication_tag=_fixture_tag(
            b"NCP-B01-SYNTHETIC-VALIDATED-RELEASE-CAS-RECEIPT-V1",
            receipt.semantic_receipt_digest,
            fixture_key=fixture_key,
        ),
    )


def validated_release_cas_receipt_artifact_digest(
    receipt: SyntheticValidatedObserverReadReleaseCASReceipt,
) -> str:
    return _domain_digest(
        "ncp.b01.bridge.SyntheticValidatedObserverReadReleaseCASReceiptArtifact@1",
        receipt,
    )


def issue_validated_release_cas_receipt(
    cas: ObserverReadReleaseCAS,
    *,
    validation_event_id: str,
    validator_identity: tuple[str, str],
    scope: CanonicalObserverReadScope,
    membership: ObserverBoundaryReadScopeMembership,
    decision: SealedObserverReadAuthorizationDecision,
    release_context: SyntheticVerifiedReleaseRecipientContext,
    qualified_deadline_mapping: QualifiedDecisionDeadlineMapping,
    grant_currentness_evidence: SyntheticAuthenticatedGrantCurrentnessEvidence,
    expected_observer_identity: tuple[str, str],
    expected_boundary_identity: tuple[str, str, str],
    expected_authorization_audience: str,
    expected_authorization_cut: ExpectedObserverReadAuthorizationCut,
    expected_issuer_identity: tuple[str, str, str],
    expected_release_recipient_identity: tuple[str, str],
    expected_release_transport_context: tuple[str, str, str],
    expected_local_security_state: tuple[str, int, int],
    expected_release_context_artifact_digest: str,
    expected_grant_currentness_state_cut: ExpectedGrantCurrentnessStateCut,
    expected_deadline_mapping_state_cut: ExpectedQualifiedDeadlineMappingStateCut,
    release_idempotency_key: str,
    expected_boundary_clock_incarnation: str,
    expected_mapping_policy_artifact_digest: str,
    checked_at: int,
    fixture_key: bytes,
) -> SyntheticValidatedObserverReadReleaseCASReceipt:
    """Validate the complete CAS chain before issuing its retained receipt."""

    _uuid4(validation_event_id, label="release CAS validation event ID")
    _require(
        type(validator_identity) is tuple and len(validator_identity) == 2,
        "release CAS validator identity is malformed",
    )
    _authority_identifier(
        validator_identity[0],
        label="release CAS validator principal",
    )
    _instance_identifier(
        validator_identity[1],
        label="release CAS validator instance",
    )
    validate_release_cas(
        cas,
        scope=scope,
        membership=membership,
        decision=decision,
        release_context=release_context,
        qualified_deadline_mapping=qualified_deadline_mapping,
        grant_currentness_evidence=grant_currentness_evidence,
        expected_observer_identity=expected_observer_identity,
        expected_boundary_identity=expected_boundary_identity,
        expected_authorization_audience=expected_authorization_audience,
        expected_authorization_cut=expected_authorization_cut,
        expected_issuer_identity=expected_issuer_identity,
        expected_release_recipient_identity=(expected_release_recipient_identity),
        expected_release_transport_context=expected_release_transport_context,
        expected_local_security_state=expected_local_security_state,
        expected_release_context_artifact_digest=(
            expected_release_context_artifact_digest
        ),
        expected_grant_currentness_state_cut=(expected_grant_currentness_state_cut),
        expected_deadline_mapping_state_cut=expected_deadline_mapping_state_cut,
        release_idempotency_key=release_idempotency_key,
        expected_boundary_clock_incarnation=(expected_boundary_clock_incarnation),
        expected_mapping_policy_artifact_digest=(
            expected_mapping_policy_artifact_digest
        ),
        checked_at=checked_at,
        fixture_key=fixture_key,
    )
    return _seal_validated_release_cas_receipt(
        SyntheticValidatedObserverReadReleaseCASReceipt(
            provenance_kind=("SYNTHETIC_FULL_OBSERVER_READ_RELEASE_CAS_VALIDATION"),
            validation_event_id=validation_event_id,
            validator_principal=validator_identity[0],
            validator_instance=validator_identity[1],
            boundary_clock_incarnation=(expected_boundary_clock_incarnation),
            release_cas_artifact_digest=cas.cas_digest,
            authorization_ingress_artifact_digest=(
                cas.authorization_ingress_artifact_digest
            ),
            release_recipient_context_artifact_digest=(
                cas.release_recipient_context_artifact_digest
            ),
            read_decision_artifact_digest=(cas.read_decision_artifact_digest),
            qualified_deadline_mapping_artifact_digest=(
                cas.qualified_deadline_mapping_artifact_digest
            ),
            grant_currentness_evidence_artifact_digest=(
                cas.grant_currentness_evidence_artifact_digest
            ),
            expected_authorization_cut_digest=(
                expected_authorization_cut_digest(expected_authorization_cut)
            ),
            expected_grant_currentness_state_cut_digest=(
                expected_grant_currentness_state_cut_digest(
                    expected_grant_currentness_state_cut
                )
            ),
            expected_deadline_mapping_state_cut_digest=(
                expected_qualified_deadline_mapping_state_cut_digest(
                    expected_deadline_mapping_state_cut
                )
            ),
            checked_at=checked_at,
            effective_release_not_after=cas.effective_release_not_after,
            semantic_receipt_digest="",
            fixture_authentication_tag="",
        ),
        fixture_key=fixture_key,
    )


def validate_validated_release_cas_receipt(
    receipt: SyntheticValidatedObserverReadReleaseCASReceipt,
    *,
    release_cas: ObserverReadReleaseCAS,
    expected_validator_identity: tuple[str, str],
    expected_boundary_clock_incarnation: str,
    expected_receipt_artifact_digest: str,
    fixture_key: bytes,
) -> None:
    _require(
        type(receipt) is SyntheticValidatedObserverReadReleaseCASReceipt,
        "validated release CAS receipt type is not exact",
    )
    _require(
        type(release_cas) is ObserverReadReleaseCAS
        and release_cas.cas_digest == release_cas_digest(release_cas),
        "validated release CAS receipt does not receive an exact CAS",
    )
    _require(
        type(expected_validator_identity) is tuple
        and len(expected_validator_identity) == 2,
        "expected release CAS validator identity is malformed",
    )
    _authority_identifier(
        receipt.validator_principal,
        label="release CAS receipt validator principal",
    )
    _instance_identifier(
        receipt.validator_instance,
        label="release CAS receipt validator instance",
    )
    _authority_identifier(
        expected_validator_identity[0],
        label="expected release CAS validator principal",
    )
    _instance_identifier(
        expected_validator_identity[1],
        label="expected release CAS validator instance",
    )
    _uuid4(
        receipt.validation_event_id,
        label="release CAS receipt validation event",
    )
    _uuid4(
        receipt.boundary_clock_incarnation,
        label="release CAS receipt boundary clock",
    )
    _uuid4(
        expected_boundary_clock_incarnation,
        label="expected release CAS receipt boundary clock",
    )
    for value, label in (
        (
            receipt.release_cas_artifact_digest,
            "validated release CAS receipt CAS digest",
        ),
        (
            receipt.authorization_ingress_artifact_digest,
            "validated release CAS receipt authorization ingress",
        ),
        (
            receipt.release_recipient_context_artifact_digest,
            "validated release CAS receipt recipient context",
        ),
        (
            receipt.read_decision_artifact_digest,
            "validated release CAS receipt decision",
        ),
        (
            receipt.qualified_deadline_mapping_artifact_digest,
            "validated release CAS receipt deadline mapping",
        ),
        (
            receipt.grant_currentness_evidence_artifact_digest,
            "validated release CAS receipt currentness",
        ),
        (
            receipt.expected_authorization_cut_digest,
            "validated release CAS receipt authorization cut",
        ),
        (
            receipt.expected_grant_currentness_state_cut_digest,
            "validated release CAS receipt currentness cut",
        ),
        (
            receipt.expected_deadline_mapping_state_cut_digest,
            "validated release CAS receipt deadline mapping cut",
        ),
        (
            receipt.semantic_receipt_digest,
            "validated release CAS receipt semantic digest",
        ),
        (
            receipt.fixture_authentication_tag,
            "validated release CAS receipt fixture tag",
        ),
        (
            expected_receipt_artifact_digest,
            "expected validated release CAS receipt artifact",
        ),
    ):
        _digest64(value, label=label, authority_bearing=True)
    _require(
        receipt.provenance_kind == "SYNTHETIC_FULL_OBSERVER_READ_RELEASE_CAS_VALIDATION"
        and (
            receipt.validator_principal,
            receipt.validator_instance,
        )
        == expected_validator_identity
        and receipt.boundary_clock_incarnation
        == expected_boundary_clock_incarnation
        == release_cas.boundary_clock_incarnation
        and receipt.release_cas_artifact_digest == release_cas.cas_digest
        and receipt.authorization_ingress_artifact_digest
        == release_cas.authorization_ingress_artifact_digest
        and receipt.release_recipient_context_artifact_digest
        == release_cas.release_recipient_context_artifact_digest
        and receipt.read_decision_artifact_digest
        == release_cas.read_decision_artifact_digest
        and receipt.qualified_deadline_mapping_artifact_digest
        == release_cas.qualified_deadline_mapping_artifact_digest
        and receipt.grant_currentness_evidence_artifact_digest
        == release_cas.grant_currentness_evidence_artifact_digest
        and type(receipt.checked_at) is int
        and type(receipt.effective_release_not_after) is int
        and 0
        <= receipt.checked_at
        < receipt.effective_release_not_after
        == release_cas.effective_release_not_after
        <= MAX_SAFE_INTEGER
        and validated_release_cas_receipt_artifact_digest(receipt)
        == expected_receipt_artifact_digest
        and receipt.semantic_receipt_digest
        == validated_release_cas_receipt_semantic_digest(receipt)
        and hmac.compare_digest(
            receipt.fixture_authentication_tag,
            _fixture_tag(
                b"NCP-B01-SYNTHETIC-VALIDATED-RELEASE-CAS-RECEIPT-V1",
                receipt.semantic_receipt_digest,
                fixture_key=fixture_key,
            ),
        ),
        "validated release CAS receipt does not bind the exact fully checked "
        "CAS, validator, boundary clock, deadline, or retained artifact",
    )


@dataclass(frozen=True, slots=True)
class SyntheticCommittedObserverReadOutboxArtifact:
    provenance_kind: str
    stable_outbox_item_id: str
    exact_payload: bytes
    stable_payload_digest: str
    payload_octet_length: int
    release_cas_artifact_digest: str
    release_recipient_context_artifact_digest: str
    boundary_principal: str
    boundary_instance: str
    recipient_principal: str
    recipient_instance: str
    canonical_scope_digest: str
    boundary_scope_membership_digest: str
    release_idempotency_key: str
    transport_idempotency_key: str
    release_ordinal: int
    installed_release_counter_state_digest: str
    boundary_clock_incarnation: str
    committed_at: int
    effective_release_not_after: int
    outbox_identity_digest: str
    semantic_artifact_digest: str
    fixture_authentication_tag: str


def immutable_payload_digest(payload: bytes) -> str:
    _require(
        type(payload) is bytes and 0 < len(payload) <= MAX_BRIDGE_PAYLOAD_OCTETS,
        "committed outbox payload must be bounded immutable bytes",
    )
    return hashlib.sha256(payload).hexdigest()


def committed_outbox_identity_digest(
    artifact: SyntheticCommittedObserverReadOutboxArtifact,
) -> str:
    return _owned_json_domain_digest(
        "ncp.b01.bridge.ObserverReadCommittedOutboxIdentity@1",
        {
            "boundary_instance": artifact.boundary_instance,
            "boundary_principal": artifact.boundary_principal,
            "boundary_scope_membership_digest": (
                artifact.boundary_scope_membership_digest
            ),
            "canonical_scope_digest": artifact.canonical_scope_digest,
            "installed_release_counter_state_digest": (
                artifact.installed_release_counter_state_digest
            ),
            "payload_octet_length": artifact.payload_octet_length,
            "recipient_instance": artifact.recipient_instance,
            "recipient_principal": artifact.recipient_principal,
            "release_cas_artifact_digest": artifact.release_cas_artifact_digest,
            "release_idempotency_key": artifact.release_idempotency_key,
            "release_ordinal": artifact.release_ordinal,
            "stable_outbox_item_id": artifact.stable_outbox_item_id,
            "stable_payload_digest": artifact.stable_payload_digest,
            "transport_idempotency_key": artifact.transport_idempotency_key,
        },
    )


def committed_outbox_semantic_digest(
    artifact: SyntheticCommittedObserverReadOutboxArtifact,
) -> str:
    return _owned_json_domain_digest(
        "ncp.b01.bridge.SyntheticCommittedObserverReadOutboxArtifact@1",
        _registered_artifact_projection(
            artifact,
            expected_type=SyntheticCommittedObserverReadOutboxArtifact,
            excluded_fields=frozenset(
                {"fixture_authentication_tag", "semantic_artifact_digest"}
            ),
        ),
    )


def seal_committed_outbox_artifact(
    artifact: SyntheticCommittedObserverReadOutboxArtifact,
    *,
    fixture_key: bytes,
) -> SyntheticCommittedObserverReadOutboxArtifact:
    artifact = replace(
        artifact,
        stable_payload_digest=immutable_payload_digest(artifact.exact_payload),
        payload_octet_length=len(artifact.exact_payload),
    )
    artifact = replace(
        artifact,
        outbox_identity_digest=committed_outbox_identity_digest(artifact),
    )
    artifact = replace(
        artifact,
        semantic_artifact_digest=committed_outbox_semantic_digest(artifact),
    )
    return replace(
        artifact,
        fixture_authentication_tag=_fixture_tag(
            b"NCP-B01-SYNTHETIC-COMMITTED-OBSERVER-READ-OUTBOX-V1",
            artifact.semantic_artifact_digest,
            fixture_key=fixture_key,
        ),
    )


def committed_outbox_artifact_digest(
    artifact: SyntheticCommittedObserverReadOutboxArtifact,
) -> str:
    return _domain_digest(
        "ncp.b01.bridge.SyntheticCommittedObserverReadOutboxArtifactDigest@1",
        artifact,
    )


@dataclass(frozen=True, slots=True)
class SyntheticObserverReadOutboxCommitReceipt:
    provenance_kind: str
    transaction_id: str
    boundary_principal: str
    boundary_instance: str
    boundary_clock_incarnation: str
    prior_storage_state_head_digest: str
    installed_storage_state_head_digest: str
    validated_release_cas_receipt_artifact_digest: str
    release_cas_artifact_digest: str
    committed_outbox_artifact_digest: str
    stable_outbox_item_id: str
    outbox_identity_digest: str
    installed_release_counter_state_digest: str
    release_ordinal: int
    committed_at: int
    semantic_receipt_digest: str
    fixture_authentication_tag: str


@dataclass(frozen=True, slots=True)
class ExpectedCommittedObserverReadOutboxStateCut:
    transaction_id: str
    prior_storage_state_head_digest: str
    installed_storage_state_head_digest: str
    validated_release_cas_receipt_artifact_digest: str
    committed_outbox_artifact_digest: str
    commit_receipt_artifact_digest: str


def installed_outbox_storage_state_head_digest(
    receipt: SyntheticObserverReadOutboxCommitReceipt,
) -> str:
    return _owned_json_domain_digest(
        "ncp.b01.bridge.ObserverReadInstalledOutboxStorageStateHead@1",
        {
            "boundary_clock_incarnation": (receipt.boundary_clock_incarnation),
            "boundary_instance": receipt.boundary_instance,
            "boundary_principal": receipt.boundary_principal,
            "committed_at": receipt.committed_at,
            "committed_outbox_artifact_digest": (
                receipt.committed_outbox_artifact_digest
            ),
            "installed_release_counter_state_digest": (
                receipt.installed_release_counter_state_digest
            ),
            "outbox_identity_digest": receipt.outbox_identity_digest,
            "prior_storage_state_head_digest": (
                receipt.prior_storage_state_head_digest
            ),
            "release_cas_artifact_digest": (receipt.release_cas_artifact_digest),
            "release_ordinal": receipt.release_ordinal,
            "stable_outbox_item_id": receipt.stable_outbox_item_id,
            "transaction_id": receipt.transaction_id,
            "validated_release_cas_receipt_artifact_digest": (
                receipt.validated_release_cas_receipt_artifact_digest
            ),
        },
    )


def outbox_commit_receipt_semantic_digest(
    receipt: SyntheticObserverReadOutboxCommitReceipt,
) -> str:
    return _owned_json_domain_digest(
        "ncp.b01.bridge.SyntheticObserverReadOutboxCommitReceipt@1",
        _registered_artifact_projection(
            receipt,
            expected_type=SyntheticObserverReadOutboxCommitReceipt,
            excluded_fields=frozenset(
                {"fixture_authentication_tag", "semantic_receipt_digest"}
            ),
        ),
    )


def seal_outbox_commit_receipt(
    receipt: SyntheticObserverReadOutboxCommitReceipt,
    *,
    fixture_key: bytes,
) -> SyntheticObserverReadOutboxCommitReceipt:
    receipt = replace(
        receipt,
        installed_storage_state_head_digest=(
            installed_outbox_storage_state_head_digest(receipt)
        ),
    )
    receipt = replace(
        receipt,
        semantic_receipt_digest=outbox_commit_receipt_semantic_digest(receipt),
    )
    return replace(
        receipt,
        fixture_authentication_tag=_fixture_tag(
            b"NCP-B01-SYNTHETIC-OBSERVER-READ-OUTBOX-COMMIT-RECEIPT-V1",
            receipt.semantic_receipt_digest,
            fixture_key=fixture_key,
        ),
    )


def outbox_commit_receipt_artifact_digest(
    receipt: SyntheticObserverReadOutboxCommitReceipt,
) -> str:
    return _domain_digest(
        "ncp.b01.bridge.SyntheticObserverReadOutboxCommitReceiptArtifact@1",
        receipt,
    )


def validate_expected_committed_outbox_state_cut(
    cut: ExpectedCommittedObserverReadOutboxStateCut,
) -> None:
    _require(
        type(cut) is ExpectedCommittedObserverReadOutboxStateCut,
        "expected committed outbox state cut type is not exact",
    )
    _uuid4(cut.transaction_id, label="expected outbox transaction ID")
    for value, label in (
        (cut.prior_storage_state_head_digest, "expected prior storage head"),
        (
            cut.installed_storage_state_head_digest,
            "expected installed storage head",
        ),
        (
            cut.validated_release_cas_receipt_artifact_digest,
            "expected validated release CAS receipt",
        ),
        (
            cut.committed_outbox_artifact_digest,
            "expected committed outbox artifact",
        ),
        (
            cut.commit_receipt_artifact_digest,
            "expected outbox commit receipt",
        ),
    ):
        _digest64(value, label=label, authority_bearing=True)


def validate_outbox_commit_receipt(
    receipt: SyntheticObserverReadOutboxCommitReceipt,
    *,
    committed_outbox: SyntheticCommittedObserverReadOutboxArtifact,
    release_cas: ObserverReadReleaseCAS,
    validated_release_cas_receipt: (SyntheticValidatedObserverReadReleaseCASReceipt),
    expected_state_cut: ExpectedCommittedObserverReadOutboxStateCut,
    expected_boundary_identity: tuple[str, str, str],
    expected_boundary_clock_incarnation: str,
    fixture_key: bytes,
) -> None:
    _require(
        type(receipt) is SyntheticObserverReadOutboxCommitReceipt,
        "outbox commit receipt type is not exact",
    )
    _require(
        type(committed_outbox) is SyntheticCommittedObserverReadOutboxArtifact,
        "outbox commit receipt committed artifact type is not exact",
    )
    _require(
        type(expected_boundary_identity) is tuple
        and len(expected_boundary_identity) == 3,
        "expected outbox commit boundary identity is malformed",
    )
    _authority_identifier(
        expected_boundary_identity[0],
        label="expected outbox commit boundary principal",
    )
    _instance_identifier(
        expected_boundary_identity[1],
        label="expected outbox commit boundary instance",
    )
    _authority_identifier(
        expected_boundary_identity[2],
        label="expected outbox commit deadline policy",
    )
    validate_expected_committed_outbox_state_cut(expected_state_cut)
    validate_validated_release_cas_receipt(
        validated_release_cas_receipt,
        release_cas=release_cas,
        expected_validator_identity=(
            expected_boundary_identity[0],
            expected_boundary_identity[1],
        ),
        expected_boundary_clock_incarnation=(expected_boundary_clock_incarnation),
        expected_receipt_artifact_digest=(
            expected_state_cut.validated_release_cas_receipt_artifact_digest
        ),
        fixture_key=fixture_key,
    )
    _authority_identifier(
        receipt.boundary_principal,
        label="outbox commit receipt boundary principal",
    )
    _instance_identifier(
        receipt.boundary_instance,
        label="outbox commit receipt boundary instance",
    )
    _uuid4(receipt.transaction_id, label="outbox commit transaction ID")
    _uuid4(
        receipt.boundary_clock_incarnation,
        label="outbox commit receipt boundary clock",
    )
    _uuid4(
        receipt.stable_outbox_item_id,
        label="outbox commit receipt stable item ID",
    )
    for value, label in (
        (
            receipt.prior_storage_state_head_digest,
            "outbox commit prior storage head",
        ),
        (
            receipt.installed_storage_state_head_digest,
            "outbox commit installed storage head",
        ),
        (
            receipt.validated_release_cas_receipt_artifact_digest,
            "outbox commit validated release CAS receipt",
        ),
        (receipt.release_cas_artifact_digest, "outbox commit release CAS"),
        (
            receipt.committed_outbox_artifact_digest,
            "outbox commit committed artifact",
        ),
        (receipt.outbox_identity_digest, "outbox commit identity"),
        (
            receipt.installed_release_counter_state_digest,
            "outbox commit installed quota head",
        ),
        (
            receipt.semantic_receipt_digest,
            "outbox commit semantic receipt",
        ),
        (
            receipt.fixture_authentication_tag,
            "outbox commit fixture tag",
        ),
    ):
        _digest64(value, label=label, authority_bearing=True)
    _require(
        receipt.provenance_kind == "SYNTHETIC_ATOMIC_OBSERVER_READ_OUTBOX_COMMIT"
        and (
            receipt.boundary_principal,
            receipt.boundary_instance,
        )
        == expected_boundary_identity[:2]
        and receipt.boundary_clock_incarnation
        == expected_boundary_clock_incarnation
        == release_cas.boundary_clock_incarnation
        and receipt.transaction_id == expected_state_cut.transaction_id
        and receipt.prior_storage_state_head_digest
        == expected_state_cut.prior_storage_state_head_digest
        and receipt.installed_storage_state_head_digest
        == expected_state_cut.installed_storage_state_head_digest
        == installed_outbox_storage_state_head_digest(receipt)
        and receipt.validated_release_cas_receipt_artifact_digest
        == expected_state_cut.validated_release_cas_receipt_artifact_digest
        == validated_release_cas_receipt_artifact_digest(validated_release_cas_receipt)
        and receipt.release_cas_artifact_digest == release_cas.cas_digest
        and receipt.committed_outbox_artifact_digest
        == expected_state_cut.committed_outbox_artifact_digest
        == committed_outbox_artifact_digest(committed_outbox)
        and receipt.stable_outbox_item_id == committed_outbox.stable_outbox_item_id
        and receipt.outbox_identity_digest == committed_outbox.outbox_identity_digest
        and receipt.installed_release_counter_state_digest
        == committed_outbox.installed_release_counter_state_digest
        == release_cas.next_release_counter_state_digest
        and receipt.release_ordinal
        == committed_outbox.release_ordinal
        == release_cas.release_ordinal
        and type(receipt.release_ordinal) is int
        and 0 < receipt.release_ordinal <= MAX_SAFE_INTEGER
        and type(receipt.committed_at) is int
        and receipt.committed_at == committed_outbox.committed_at
        and 0
        <= validated_release_cas_receipt.checked_at
        <= receipt.committed_at
        < committed_outbox.effective_release_not_after
        <= MAX_SAFE_INTEGER
        and outbox_commit_receipt_artifact_digest(receipt)
        == expected_state_cut.commit_receipt_artifact_digest
        and receipt.semantic_receipt_digest
        == outbox_commit_receipt_semantic_digest(receipt)
        and hmac.compare_digest(
            receipt.fixture_authentication_tag,
            _fixture_tag(
                b"NCP-B01-SYNTHETIC-OBSERVER-READ-OUTBOX-COMMIT-RECEIPT-V1",
                receipt.semantic_receipt_digest,
                fixture_key=fixture_key,
            ),
        ),
        "outbox commit receipt does not atomically bind the prior head, CAS "
        "successor, stable outbox artifact, installed head, or retained cut",
    )


def validate_committed_outbox_artifact(
    artifact: SyntheticCommittedObserverReadOutboxArtifact,
    *,
    scope: CanonicalObserverReadScope,
    membership: ObserverBoundaryReadScopeMembership,
    release_cas: ObserverReadReleaseCAS,
    validated_release_cas_receipt: (SyntheticValidatedObserverReadReleaseCASReceipt),
    commit_receipt: SyntheticObserverReadOutboxCommitReceipt,
    expected_commit_state_cut: ExpectedCommittedObserverReadOutboxStateCut,
    release_context: SyntheticVerifiedReleaseRecipientContext,
    expected_boundary_identity: tuple[str, str, str],
    expected_recipient_identity: tuple[str, str],
    expected_boundary_clock_incarnation: str,
    expected_stable_outbox_item_id: str,
    expected_exact_payload: bytes,
    expected_transport_idempotency_key: str,
    expected_artifact_digest: str,
    checked_at: int,
    fixture_key: bytes,
) -> None:
    _require(
        type(artifact) is SyntheticCommittedObserverReadOutboxArtifact,
        "committed outbox artifact type is not exact",
    )
    validate_scope(scope)
    validate_boundary_membership(
        membership,
        scope=scope,
        expected_boundary_identity=expected_boundary_identity,
    )
    validate_outbox_commit_receipt(
        commit_receipt,
        committed_outbox=artifact,
        release_cas=release_cas,
        validated_release_cas_receipt=validated_release_cas_receipt,
        expected_state_cut=expected_commit_state_cut,
        expected_boundary_identity=expected_boundary_identity,
        expected_boundary_clock_incarnation=(expected_boundary_clock_incarnation),
        fixture_key=fixture_key,
    )
    _require(
        type(release_context) is SyntheticVerifiedReleaseRecipientContext,
        "committed outbox release recipient context type is not exact",
    )
    _require(
        type(expected_recipient_identity) is tuple
        and len(expected_recipient_identity) == 2,
        "expected committed outbox recipient identity is malformed",
    )
    _authority_identifier(
        artifact.boundary_principal,
        label="committed outbox boundary principal",
    )
    _instance_identifier(
        artifact.boundary_instance,
        label="committed outbox boundary instance",
    )
    _authority_identifier(
        artifact.recipient_principal,
        label="committed outbox recipient principal",
    )
    _instance_identifier(
        artifact.recipient_instance,
        label="committed outbox recipient instance",
    )
    _uuid4(
        artifact.boundary_clock_incarnation,
        label="committed outbox boundary clock",
    )
    _uuid4(
        expected_boundary_clock_incarnation,
        label="expected committed outbox boundary clock",
    )
    for value, label in (
        (artifact.stable_outbox_item_id, "committed outbox stable item ID"),
        (artifact.release_idempotency_key, "committed outbox release idempotency"),
        (
            artifact.transport_idempotency_key,
            "committed outbox transport idempotency",
        ),
        (expected_stable_outbox_item_id, "expected committed outbox item ID"),
        (
            expected_transport_idempotency_key,
            "expected committed outbox transport idempotency",
        ),
    ):
        _uuid4(value, label=label)
    for value, label in (
        (artifact.stable_payload_digest, "committed outbox payload digest"),
        (artifact.release_cas_artifact_digest, "committed outbox CAS digest"),
        (
            artifact.release_recipient_context_artifact_digest,
            "committed outbox recipient context artifact digest",
        ),
        (artifact.canonical_scope_digest, "committed outbox scope digest"),
        (
            artifact.boundary_scope_membership_digest,
            "committed outbox membership digest",
        ),
        (
            artifact.installed_release_counter_state_digest,
            "committed outbox installed quota state",
        ),
        (artifact.outbox_identity_digest, "committed outbox identity digest"),
        (
            artifact.semantic_artifact_digest,
            "committed outbox semantic artifact digest",
        ),
        (
            artifact.fixture_authentication_tag,
            "committed outbox fixture authentication tag",
        ),
        (expected_artifact_digest, "expected committed outbox artifact digest"),
    ):
        _digest64(value, label=label, authority_bearing=True)
    expected_stable_payload_digest = immutable_payload_digest(expected_exact_payload)
    expected_payload_octet_length = len(expected_exact_payload)
    _require(
        artifact.exact_payload == expected_exact_payload,
        "committed outbox payload bytes differ from the retained payload",
    )
    integer_fields = (
        artifact.payload_octet_length,
        artifact.release_ordinal,
        artifact.committed_at,
        artifact.effective_release_not_after,
        expected_payload_octet_length,
        checked_at,
    )
    _require(
        all(
            type(value) is int and 0 <= value <= MAX_SAFE_INTEGER
            for value in integer_fields
        )
        and artifact.payload_octet_length > 0
        and artifact.release_ordinal > 0,
        "committed outbox size, ordinal, or time is invalid",
    )
    _require(
        artifact.provenance_kind
        == "SYNTHETIC_ATOMICALLY_COMMITTED_OBSERVER_READ_OUTBOX"
        and artifact.stable_outbox_item_id == expected_stable_outbox_item_id
        and artifact.stable_payload_digest == expected_stable_payload_digest
        and artifact.payload_octet_length == expected_payload_octet_length
        and artifact.stable_payload_digest
        == immutable_payload_digest(artifact.exact_payload)
        and artifact.payload_octet_length == len(artifact.exact_payload)
        and artifact.release_cas_artifact_digest == release_cas.cas_digest
        and artifact.release_recipient_context_artifact_digest
        == release_recipient_artifact_digest(release_context)
        and (
            artifact.boundary_principal,
            artifact.boundary_instance,
        )
        == (
            membership.boundary_principal,
            membership.boundary_instance,
        )
        and (
            artifact.recipient_principal,
            artifact.recipient_instance,
        )
        == expected_recipient_identity
        == (
            release_context.recipient_principal,
            release_context.recipient_instance,
        )
        and artifact.canonical_scope_digest == scope.scope_digest
        and artifact.boundary_scope_membership_digest == membership.membership_digest
        and artifact.release_idempotency_key == release_cas.release_idempotency_key
        and artifact.transport_idempotency_key == expected_transport_idempotency_key
        and artifact.release_ordinal == release_cas.release_ordinal
        and artifact.installed_release_counter_state_digest
        == release_cas.next_release_counter_state_digest
        and artifact.boundary_clock_incarnation
        == expected_boundary_clock_incarnation
        == release_cas.boundary_clock_incarnation
        == release_context.boundary_clock_incarnation
        and artifact.effective_release_not_after
        == release_cas.effective_release_not_after
        and 0
        <= artifact.committed_at
        <= checked_at
        < artifact.effective_release_not_after
        <= MAX_SAFE_INTEGER,
        "committed outbox does not bind the exact CAS, recipient, quota "
        "successor, payload, boundary clock, or effective deadline",
    )
    _require(
        artifact.outbox_identity_digest == committed_outbox_identity_digest(artifact)
        and committed_outbox_artifact_digest(artifact) == expected_artifact_digest
        and artifact.semantic_artifact_digest
        == committed_outbox_semantic_digest(artifact)
        and hmac.compare_digest(
            artifact.fixture_authentication_tag,
            _fixture_tag(
                b"NCP-B01-SYNTHETIC-COMMITTED-OBSERVER-READ-OUTBOX-V1",
                artifact.semantic_artifact_digest,
                fixture_key=fixture_key,
            ),
        ),
        "committed outbox identity, artifact digest, or fixture seal is invalid",
    )


@dataclass(frozen=True, slots=True)
class ExpectedDispatchDestinationCut:
    boundary_principal: str
    boundary_instance: str
    recipient_principal: str
    recipient_instance: str
    canonical_scope_digest: str
    boundary_scope_membership_digest: str
    stable_outbox_item_id: str
    endpoint_profile: str
    connection_instance: str
    replay_domain: str
    boundary_clock_incarnation: str
    local_security_state_digest: str
    local_security_epoch: int
    local_revocation_epoch: int
    transport_gate_state_digest: str
    transport_gate_epoch: int
    exclusive_not_after: int


def dispatch_transport_gate_state_digest(
    cut: ExpectedDispatchDestinationCut,
) -> str:
    """Derive the complete per-attempt open-gate state from its exact cut."""

    _require(
        type(cut) is ExpectedDispatchDestinationCut,
        "transport gate cut type is not exact",
    )
    return _domain_digest(
        "ncp.b01.bridge.SyntheticTrustedDeliveryExternalTransportGateState@1",
        (
            cut.boundary_principal,
            cut.boundary_instance,
            cut.recipient_principal,
            cut.recipient_instance,
            cut.stable_outbox_item_id,
            (
                cut.endpoint_profile,
                cut.connection_instance,
                cut.replay_domain,
            ),
            cut.local_security_state_digest,
            cut.local_security_epoch,
            cut.local_revocation_epoch,
            cut.transport_gate_epoch,
            "OPEN_FOR_EXACT_COMMITTED_ITEM",
        ),
    )


def validate_expected_dispatch_destination_cut(
    cut: ExpectedDispatchDestinationCut,
) -> None:
    _require(
        type(cut) is ExpectedDispatchDestinationCut,
        "expected dispatch destination cut type is not exact",
    )
    for value, label in (
        (cut.boundary_principal, "expected dispatch boundary principal"),
        (cut.recipient_principal, "expected dispatch recipient principal"),
    ):
        _authority_identifier(value, label=label)
    for value, label in (
        (cut.boundary_instance, "expected dispatch boundary instance"),
        (cut.recipient_instance, "expected dispatch recipient instance"),
    ):
        _instance_identifier(value, label=label)
    _validate_expected_transport_context(
        (
            cut.endpoint_profile,
            cut.connection_instance,
            cut.replay_domain,
        ),
        label="expected dispatch transport context",
    )
    _uuid4(
        cut.boundary_clock_incarnation,
        label="expected dispatch boundary clock incarnation",
    )
    _uuid4(cut.stable_outbox_item_id, label="expected dispatch outbox item ID")
    for value, label in (
        (cut.canonical_scope_digest, "expected dispatch scope digest"),
        (
            cut.boundary_scope_membership_digest,
            "expected dispatch membership digest",
        ),
        (
            cut.local_security_state_digest,
            "expected dispatch security state digest",
        ),
        (
            cut.transport_gate_state_digest,
            "expected dispatch transport gate state digest",
        ),
    ):
        _digest64(value, label=label, authority_bearing=True)
    _require(
        type(cut.local_security_epoch) is int
        and 0 < cut.local_security_epoch <= MAX_SAFE_INTEGER
        and type(cut.local_revocation_epoch) is int
        and 0 < cut.local_revocation_epoch <= MAX_SAFE_INTEGER
        and type(cut.transport_gate_epoch) is int
        and 0 < cut.transport_gate_epoch <= MAX_SAFE_INTEGER
        and type(cut.exclusive_not_after) is int
        and 0 < cut.exclusive_not_after <= MAX_SAFE_INTEGER,
        "expected dispatch destination epochs or deadline are invalid",
    )
    _require(
        cut.transport_gate_state_digest == dispatch_transport_gate_state_digest(cut),
        "expected dispatch transport gate digest is not derived from its cut",
    )


def dispatch_destination_cut_digest(
    cut: ExpectedDispatchDestinationCut,
) -> str:
    """Return the domain-separated identity of one explicit destination cut."""

    validate_expected_dispatch_destination_cut(cut)
    return _domain_digest(
        "ncp.b01.bridge.ExpectedDispatchDestinationCut@1",
        cut,
    )


def dispatch_stable_destination_digest(
    cut: ExpectedDispatchDestinationCut,
) -> str:
    """Bind retry identity without freezing the per-attempt live gate epoch."""

    validate_expected_dispatch_destination_cut(cut)
    return _domain_digest(
        "ncp.b01.bridge.StableDispatchDestinationIdentity@1",
        (
            cut.boundary_principal,
            cut.boundary_instance,
            cut.recipient_principal,
            cut.recipient_instance,
            cut.canonical_scope_digest,
            cut.boundary_scope_membership_digest,
            cut.stable_outbox_item_id,
            cut.endpoint_profile,
            cut.connection_instance,
            cut.replay_domain,
            cut.boundary_clock_incarnation,
            cut.local_security_state_digest,
            cut.local_security_epoch,
            cut.local_revocation_epoch,
            cut.exclusive_not_after,
        ),
    )


@dataclass(frozen=True, slots=True)
class SyntheticAuthenticatedDispatchContext:
    provenance_kind: str
    dispatch_verification_event_id: str
    dispatch_attempt_id: str
    boundary_principal: str
    boundary_instance: str
    recipient_principal: str
    recipient_instance: str
    canonical_scope_digest: str
    boundary_scope_membership_digest: str
    stable_outbox_item_id: str
    stable_payload_digest: str
    payload_octet_length: int
    committed_outbox_artifact_digest: str
    validated_release_cas_receipt_artifact_digest: str
    outbox_commit_receipt_artifact_digest: str
    installed_outbox_storage_state_head_digest: str
    outbox_transaction_id: str
    outbox_identity_digest: str
    release_cas_artifact_digest: str
    release_recipient_context_artifact_digest: str
    release_ordinal: int
    installed_release_counter_state_digest: str
    transport_idempotency_key: str
    endpoint_profile: str
    connection_instance: str
    replay_domain: str
    destination_cut_digest: str
    transport_gate_state_digest: str
    transport_gate_epoch: int
    boundary_clock_incarnation: str
    local_security_state_digest: str
    local_security_epoch: int
    local_revocation_epoch: int
    verified_at: int
    exclusive_not_after: int
    semantic_context_digest: str
    fixture_authentication_tag: str


def dispatch_semantic_digest(
    context: SyntheticAuthenticatedDispatchContext,
) -> str:
    return _owned_json_domain_digest(
        "ncp.b01.bridge.SyntheticAuthenticatedDispatchContext@1",
        _registered_artifact_projection(
            context,
            expected_type=SyntheticAuthenticatedDispatchContext,
            excluded_fields=frozenset(
                {"fixture_authentication_tag", "semantic_context_digest"}
            ),
        ),
    )


def seal_dispatch_context(
    context: SyntheticAuthenticatedDispatchContext,
    *,
    fixture_key: bytes,
) -> SyntheticAuthenticatedDispatchContext:
    context = replace(
        context,
        semantic_context_digest=dispatch_semantic_digest(context),
    )
    return replace(
        context,
        fixture_authentication_tag=_fixture_tag(
            b"NCP-B01-SYNTHETIC-AUTHENTICATED-DISPATCH-CONTEXT-V1",
            context.semantic_context_digest,
            fixture_key=fixture_key,
        ),
    )


def dispatch_artifact_digest(
    context: SyntheticAuthenticatedDispatchContext,
) -> str:
    return _domain_digest(
        "ncp.b01.bridge.SyntheticAuthenticatedDispatchArtifact@1",
        context,
    )


def validate_dispatch_context(
    context: SyntheticAuthenticatedDispatchContext,
    *,
    scope: CanonicalObserverReadScope,
    membership: ObserverBoundaryReadScopeMembership,
    release_context: SyntheticVerifiedReleaseRecipientContext,
    release_cas: ObserverReadReleaseCAS,
    validated_release_cas_receipt: (SyntheticValidatedObserverReadReleaseCASReceipt),
    committed_outbox: SyntheticCommittedObserverReadOutboxArtifact,
    commit_receipt: SyntheticObserverReadOutboxCommitReceipt,
    expected_commit_state_cut: ExpectedCommittedObserverReadOutboxStateCut,
    expected_boundary_identity: tuple[str, str, str],
    expected_recipient_identity: tuple[str, str],
    expected_release_transport_context: tuple[str, str, str],
    expected_release_security_state: tuple[str, int, int],
    expected_boundary_clock_incarnation: str,
    expected_release_context_artifact_digest: str,
    release_context_checked_at: int,
    expected_stable_outbox_item_id: str,
    actual_dispatch_payload: bytes,
    expected_committed_outbox_artifact_digest: str,
    expected_dispatch_attempt_id: str,
    expected_transport_idempotency_key: str,
    expected_local_security_state: tuple[str, int, int],
    expected_destination_cut: ExpectedDispatchDestinationCut,
    expected_dispatch_context_artifact_digest: str,
    checked_at: int,
    fixture_key: bytes,
) -> None:
    _require(
        type(context) is SyntheticAuthenticatedDispatchContext,
        "dispatch context type is not exact",
    )
    validate_scope(scope)
    validate_boundary_membership(
        membership,
        scope=scope,
        expected_boundary_identity=expected_boundary_identity,
    )
    validate_expected_dispatch_destination_cut(expected_destination_cut)
    validate_release_recipient_context(
        release_context,
        membership=membership,
        expected_recipient_identity=expected_recipient_identity,
        expected_transport_context=expected_release_transport_context,
        expected_local_security_state=expected_release_security_state,
        expected_boundary_clock_incarnation=(expected_boundary_clock_incarnation),
        expected_context_artifact_digest=(expected_release_context_artifact_digest),
        checked_at=release_context_checked_at,
        fixture_key=fixture_key,
    )
    validate_committed_outbox_artifact(
        committed_outbox,
        scope=scope,
        membership=membership,
        release_cas=release_cas,
        validated_release_cas_receipt=validated_release_cas_receipt,
        commit_receipt=commit_receipt,
        expected_commit_state_cut=expected_commit_state_cut,
        release_context=release_context,
        expected_boundary_identity=expected_boundary_identity,
        expected_recipient_identity=expected_recipient_identity,
        expected_boundary_clock_incarnation=(expected_boundary_clock_incarnation),
        expected_stable_outbox_item_id=expected_stable_outbox_item_id,
        expected_exact_payload=committed_outbox.exact_payload,
        expected_transport_idempotency_key=(expected_transport_idempotency_key),
        expected_artifact_digest=(expected_committed_outbox_artifact_digest),
        checked_at=checked_at,
        fixture_key=fixture_key,
    )
    for value, label in (
        (context.boundary_principal, "dispatch boundary principal"),
        (context.recipient_principal, "dispatch recipient principal"),
        (context.replay_domain, "dispatch replay domain"),
    ):
        _authority_identifier(value, label=label)
    for value, label in (
        (context.boundary_instance, "dispatch boundary instance"),
        (context.recipient_instance, "dispatch recipient instance"),
        (context.connection_instance, "dispatch connection"),
    ):
        _instance_identifier(value, label=label)
    _uuid4(
        context.dispatch_verification_event_id,
        label="dispatch verification event ID",
    )
    _uuid4(context.dispatch_attempt_id, label="dispatch attempt ID")
    _uuid4(expected_dispatch_attempt_id, label="expected dispatch attempt ID")
    _uuid4(
        context.transport_idempotency_key,
        label="dispatch transport idempotency key",
    )
    _uuid4(
        expected_transport_idempotency_key,
        label="expected dispatch transport idempotency key",
    )
    _uuid4(context.stable_outbox_item_id, label="dispatch outbox item ID")
    _uuid4(
        expected_stable_outbox_item_id,
        label="expected dispatch outbox item ID",
    )
    _uuid4(
        context.boundary_clock_incarnation,
        label="dispatch boundary clock",
    )
    _uuid4(
        expected_boundary_clock_incarnation,
        label="expected dispatch boundary clock",
    )
    _uuid4(context.outbox_transaction_id, label="dispatch outbox transaction")
    for value, label in (
        (context.stable_payload_digest, "dispatch stable payload digest"),
        (
            context.committed_outbox_artifact_digest,
            "dispatch committed outbox artifact digest",
        ),
        (
            context.validated_release_cas_receipt_artifact_digest,
            "dispatch validated release CAS receipt",
        ),
        (
            context.outbox_commit_receipt_artifact_digest,
            "dispatch outbox commit receipt",
        ),
        (
            context.installed_outbox_storage_state_head_digest,
            "dispatch installed outbox storage head",
        ),
        (context.outbox_identity_digest, "dispatch outbox identity digest"),
        (
            context.release_cas_artifact_digest,
            "dispatch release CAS artifact digest",
        ),
        (
            context.release_recipient_context_artifact_digest,
            "dispatch recipient context artifact digest",
        ),
        (
            context.installed_release_counter_state_digest,
            "dispatch installed release counter state",
        ),
        (context.canonical_scope_digest, "dispatch canonical scope digest"),
        (
            context.boundary_scope_membership_digest,
            "dispatch boundary membership digest",
        ),
        (context.destination_cut_digest, "dispatch destination cut digest"),
        (
            context.transport_gate_state_digest,
            "dispatch transport gate state digest",
        ),
    ):
        _digest64(value, label=label, authority_bearing=True)
    _closed_ascii(
        context.endpoint_profile,
        label="dispatch endpoint profile",
        maximum_bytes=32,
        identifier=True,
    )
    _digest64(
        context.local_security_state_digest,
        label="dispatch local security state digest",
        authority_bearing=True,
    )
    _require(
        type(expected_local_security_state) is tuple
        and len(expected_local_security_state) == 3
        and type(expected_local_security_state[0]) is str
        and type(expected_local_security_state[1]) is int
        and type(expected_local_security_state[2]) is int
        and type(checked_at) is int,
        "expected dispatch security cut or time is malformed",
    )
    expected_security_digest, expected_security_epoch, expected_revocation_epoch = (
        expected_local_security_state
    )
    _digest64(
        expected_security_digest,
        label="expected dispatch security state digest",
        authority_bearing=True,
    )
    _digest64(
        expected_dispatch_context_artifact_digest,
        label="expected dispatch context artifact digest",
        authority_bearing=True,
    )
    _require(
        (
            expected_destination_cut.boundary_principal,
            expected_destination_cut.boundary_instance,
            expected_destination_cut.recipient_principal,
            expected_destination_cut.recipient_instance,
        )
        == (
            expected_boundary_identity[0],
            expected_boundary_identity[1],
            expected_recipient_identity[0],
            expected_recipient_identity[1],
        )
        and expected_destination_cut.canonical_scope_digest == scope.scope_digest
        and expected_destination_cut.boundary_scope_membership_digest
        == membership.membership_digest
        and expected_destination_cut.stable_outbox_item_id
        == expected_stable_outbox_item_id
        and expected_destination_cut.boundary_clock_incarnation
        == expected_boundary_clock_incarnation
        and (
            expected_destination_cut.local_security_state_digest,
            expected_destination_cut.local_security_epoch,
            expected_destination_cut.local_revocation_epoch,
        )
        == expected_local_security_state
        and expected_destination_cut.exclusive_not_after
        <= committed_outbox.effective_release_not_after,
        "expected dispatch destination cut differs from the independently "
        "supplied destination, route, security, item, clock, or deadline",
    )
    _require(
        context.provenance_kind == "SYNTHETIC_FRESH_AUTHENTICATED_OUTBOX_DISPATCH"
        and dispatch_artifact_digest(context)
        == expected_dispatch_context_artifact_digest
        and context.endpoint_profile == "production-secure"
        and (
            context.endpoint_profile,
            context.connection_instance,
            context.replay_domain,
        )
        == (
            expected_destination_cut.endpoint_profile,
            expected_destination_cut.connection_instance,
            expected_destination_cut.replay_domain,
        )
        and context.canonical_scope_digest
        == scope.scope_digest
        == expected_destination_cut.canonical_scope_digest
        and context.boundary_scope_membership_digest
        == membership.membership_digest
        == expected_destination_cut.boundary_scope_membership_digest
        and context.destination_cut_digest
        == dispatch_destination_cut_digest(expected_destination_cut)
        and (
            context.transport_gate_state_digest,
            context.transport_gate_epoch,
        )
        == (
            expected_destination_cut.transport_gate_state_digest,
            expected_destination_cut.transport_gate_epoch,
        )
        and context.dispatch_attempt_id == expected_dispatch_attempt_id
        and context.transport_idempotency_key == expected_transport_idempotency_key
        and context.boundary_clock_incarnation
        == expected_boundary_clock_incarnation
        == committed_outbox.boundary_clock_incarnation
        == release_cas.boundary_clock_incarnation
        and (
            context.boundary_principal,
            context.boundary_instance,
            context.recipient_principal,
            context.recipient_instance,
        )
        == (
            membership.boundary_principal,
            membership.boundary_instance,
            release_context.recipient_principal,
            release_context.recipient_instance,
        )
        and context.stable_outbox_item_id
        == expected_stable_outbox_item_id
        == expected_destination_cut.stable_outbox_item_id
        == committed_outbox.stable_outbox_item_id
        and context.stable_payload_digest
        == immutable_payload_digest(actual_dispatch_payload)
        == committed_outbox.stable_payload_digest
        and context.payload_octet_length
        == len(actual_dispatch_payload)
        == committed_outbox.payload_octet_length
        and actual_dispatch_payload == committed_outbox.exact_payload
        and type(context.payload_octet_length) is int
        and 0 < context.payload_octet_length <= MAX_BRIDGE_PAYLOAD_OCTETS
        and context.committed_outbox_artifact_digest
        == committed_outbox_artifact_digest(committed_outbox)
        == expected_committed_outbox_artifact_digest
        and context.validated_release_cas_receipt_artifact_digest
        == validated_release_cas_receipt_artifact_digest(validated_release_cas_receipt)
        == expected_commit_state_cut.validated_release_cas_receipt_artifact_digest
        and context.outbox_commit_receipt_artifact_digest
        == outbox_commit_receipt_artifact_digest(commit_receipt)
        == expected_commit_state_cut.commit_receipt_artifact_digest
        and context.installed_outbox_storage_state_head_digest
        == commit_receipt.installed_storage_state_head_digest
        == expected_commit_state_cut.installed_storage_state_head_digest
        and context.outbox_transaction_id
        == commit_receipt.transaction_id
        == expected_commit_state_cut.transaction_id
        and context.outbox_identity_digest == committed_outbox.outbox_identity_digest
        and context.release_cas_artifact_digest == release_cas.cas_digest
        and context.release_recipient_context_artifact_digest
        == release_recipient_artifact_digest(release_context)
        and context.release_ordinal
        == committed_outbox.release_ordinal
        == release_cas.release_ordinal
        and context.installed_release_counter_state_digest
        == committed_outbox.installed_release_counter_state_digest
        == release_cas.next_release_counter_state_digest
        and (
            context.local_security_state_digest,
            context.local_security_epoch,
            context.local_revocation_epoch,
        )
        == (
            expected_security_digest,
            expected_security_epoch,
            expected_revocation_epoch,
        )
        == (
            expected_destination_cut.local_security_state_digest,
            expected_destination_cut.local_security_epoch,
            expected_destination_cut.local_revocation_epoch,
        )
        and type(context.local_security_epoch) is int
        and type(context.local_revocation_epoch) is int
        and type(context.transport_gate_epoch) is int
        and type(context.release_ordinal) is int
        and 0 < context.release_ordinal <= MAX_SAFE_INTEGER
        and 0 < context.local_security_epoch <= MAX_SAFE_INTEGER
        and 0 < context.local_revocation_epoch <= MAX_SAFE_INTEGER
        and 0 < context.transport_gate_epoch <= MAX_SAFE_INTEGER
        and type(context.verified_at) is int
        and type(context.exclusive_not_after) is int
        and 0
        <= committed_outbox.committed_at
        < context.verified_at
        <= checked_at
        < context.exclusive_not_after
        == expected_destination_cut.exclusive_not_after
        <= committed_outbox.effective_release_not_after
        <= MAX_SAFE_INTEGER,
        "dispatch is not a fresh post-commit authenticated context bound to "
        "the stable recipient and exact outbox artifact",
    )
    _require(
        context.semantic_context_digest == dispatch_semantic_digest(context)
        and hmac.compare_digest(
            context.fixture_authentication_tag,
            _fixture_tag(
                b"NCP-B01-SYNTHETIC-AUTHENTICATED-DISPATCH-CONTEXT-V1",
                context.semantic_context_digest,
                fixture_key=fixture_key,
            ),
        ),
        "dispatch context digest or fixture seal is invalid",
    )


@dataclass(frozen=True, slots=True)
class ExpectedObserverReadAuthorizationCut:
    authorization_ingress_artifact_digest: str
    authorization_endpoint_profile: str
    authorization_connection_instance: str
    authorization_replay_domain: str
    capability_digest: str
    capability_seal_digest: str
    capability_issuer_snapshot_digest: str
    manifest_digest: str
    manifest_entry_digest: str
    stable_grant_key_digest: str
    full_boundary_key_digest: str
    grant_digest: str
    server_entry_head_digest: str
    server_selector_digest: str
    authority_realm_key: tuple[str, str]
    source_session_kind: str
    logical_session_id: str
    source_generation: str
    security_state_digest: str
    security_epoch: int
    revocation_epoch: int
    coordinator_clock_incarnation: str
    exclusive_not_after: int
    maximum_release_count: int


def validate_expected_authorization_cut(
    cut: ExpectedObserverReadAuthorizationCut,
) -> None:
    _require(
        type(cut) is ExpectedObserverReadAuthorizationCut,
        "expected authorization cut type is not exact",
    )
    for value, label in (
        (
            cut.authorization_ingress_artifact_digest,
            "expected authorization ingress artifact digest",
        ),
        (cut.capability_digest, "expected capability digest"),
        (cut.capability_seal_digest, "expected capability seal digest"),
        (
            cut.capability_issuer_snapshot_digest,
            "expected capability issuer snapshot digest",
        ),
        (cut.manifest_digest, "expected manifest digest"),
        (cut.manifest_entry_digest, "expected manifest entry digest"),
        (cut.stable_grant_key_digest, "expected stable grant key digest"),
        (cut.full_boundary_key_digest, "expected full boundary key digest"),
        (cut.grant_digest, "expected grant digest"),
        (cut.server_entry_head_digest, "expected server entry head digest"),
        (cut.server_selector_digest, "expected server selector digest"),
        (cut.security_state_digest, "expected security state digest"),
    ):
        _digest64(value, label=label, authority_bearing=True)
    _require(
        type(cut.authority_realm_key) is tuple and len(cut.authority_realm_key) == 2,
        "expected authorization realm is malformed",
    )
    _validate_expected_transport_context(
        (
            cut.authorization_endpoint_profile,
            cut.authorization_connection_instance,
            cut.authorization_replay_domain,
        ),
        label="expected authorization cut transport context",
    )
    for index, member in enumerate(cut.authority_realm_key):
        _authority_identifier(
            member,
            label=f"expected authorization realm member {index}",
        )
    _closed_ascii(
        cut.source_session_kind,
        label="expected source session kind",
        maximum_bytes=32,
        identifier=True,
    )
    _require(
        cut.source_session_kind in SOURCE_SESSION_KINDS,
        "expected source session kind is outside the closed set",
    )
    _route_segment(cut.logical_session_id, label="expected logical session")
    _uuid4(cut.source_generation, label="expected source generation")
    _uuid4(
        cut.coordinator_clock_incarnation,
        label="expected coordinator clock incarnation",
    )
    _require(
        type(cut.security_epoch) is int
        and 0 < cut.security_epoch <= MAX_SAFE_INTEGER
        and type(cut.revocation_epoch) is int
        and 0 < cut.revocation_epoch <= MAX_SAFE_INTEGER
        and type(cut.exclusive_not_after) is int
        and 0 < cut.exclusive_not_after <= MAX_SAFE_INTEGER,
        "expected authorization cut epochs or deadline are invalid",
    )
    _require(
        type(cut.maximum_release_count) is int
        and 1 <= cut.maximum_release_count <= 4096,
        "expected authorization release quota is invalid",
    )


@dataclass(frozen=True, slots=True)
class SealedObserverReadAuthorizationDecision:
    decision_id: str
    decision_kind: str
    authority_effect: str
    caller_operation_id: str
    caller_request_digest: str
    capability_digest: str
    capability_seal_digest: str
    capability_issuer_snapshot_digest: str
    observer_principal: str
    observer_instance: str
    authorization_ingress_context: SyntheticVerifiedAuthorizationIngressContext
    manifest_digest: str
    manifest_entry_digest: str
    canonical_scope_digest: str
    boundary_scope_membership_digest: str
    stable_grant_key_digest: str
    full_boundary_key_digest: str
    grant_digest: str
    server_entry_head_digest: str
    server_selector_digest: str
    authority_realm_key: tuple[str, str]
    source_session_kind: str
    logical_session_id: str
    source_generation: str
    security_state_digest: str
    security_epoch: int
    revocation_epoch: int
    coordinator_clock_incarnation: str
    checked_at: int
    exclusive_not_after: int
    history_request_digest: str | None
    maximum_release_count: int
    issuer_principal: str
    issuer_key_id: str
    issuer_incarnation: str
    semantic_decision_digest: str
    fixture_authentication_tag: str


def semantic_read_decision_digest(
    decision: SealedObserverReadAuthorizationDecision,
) -> str:
    return _owned_json_domain_digest(
        "ncp.b01.bridge.SealedObserverReadAuthorizationDecision@1",
        _registered_artifact_projection(
            decision,
            expected_type=SealedObserverReadAuthorizationDecision,
            excluded_fields=frozenset(
                {"fixture_authentication_tag", "semantic_decision_digest"}
            ),
        ),
    )


def _decision_tag(
    decision: SealedObserverReadAuthorizationDecision,
    *,
    fixture_key: bytes,
) -> str:
    _validate_fixture_key(fixture_key)
    return hmac.new(
        fixture_key,
        b"NCP-B01-SYNTHETIC-READ-DECISION-SEAL-V1\x00"
        + decision.semantic_decision_digest.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def seal_read_decision(
    decision: SealedObserverReadAuthorizationDecision,
    *,
    fixture_key: bytes,
) -> SealedObserverReadAuthorizationDecision:
    decision = replace(
        decision,
        semantic_decision_digest=semantic_read_decision_digest(decision),
    )
    return replace(
        decision,
        fixture_authentication_tag=_decision_tag(
            decision,
            fixture_key=fixture_key,
        ),
    )


def read_decision_artifact_digest(
    decision: SealedObserverReadAuthorizationDecision,
) -> str:
    """Digest the complete sealed artifact, including its fixture-only tag."""

    return _domain_digest(
        "ncp.b01.bridge.SealedObserverReadAuthorizationArtifact@1",
        decision,
    )


def canonical_read_request_digest(
    *,
    scope: CanonicalObserverReadScope,
    membership: ObserverBoundaryReadScopeMembership,
    caller_operation_id: str,
    expected_boundary_identity: tuple[str, str, str],
) -> str:
    """Bind one caller idempotency operation to one exact read request."""

    validate_scope(scope)
    validate_boundary_membership(
        membership,
        scope=scope,
        expected_boundary_identity=expected_boundary_identity,
    )
    _uuid4(caller_operation_id, label="caller read operation ID")
    return _owned_json_domain_digest(
        "ncp.b01.bridge.CanonicalObserverReadRequest@1",
        {
            "boundary_scope_membership_digest": membership.membership_digest,
            "caller_operation_id": caller_operation_id,
            "canonical_scope_digest": scope.scope_digest,
        },
    )


def validate_read_decision(
    decision: SealedObserverReadAuthorizationDecision,
    *,
    scope: CanonicalObserverReadScope,
    membership: ObserverBoundaryReadScopeMembership,
    expected_boundary_identity: tuple[str, str, str],
    expected_observer_identity: tuple[str, str],
    expected_authorization_audience: str,
    expected_authorization_cut: ExpectedObserverReadAuthorizationCut,
    expected_issuer_identity: tuple[str, str, str],
    fixture_key: bytes,
) -> None:
    validate_scope(scope)
    validate_boundary_membership(
        membership,
        scope=scope,
        expected_boundary_identity=expected_boundary_identity,
    )
    _require(
        type(decision) is SealedObserverReadAuthorizationDecision,
        "read decision type is not exact",
    )
    _require(
        type(expected_observer_identity) is tuple
        and len(expected_observer_identity) == 2,
        "expected observer identity is malformed",
    )
    _require(
        type(expected_issuer_identity) is tuple and len(expected_issuer_identity) == 3,
        "expected issuer identity is malformed",
    )
    for value, label in (
        (expected_observer_identity[0], "expected observer principal"),
        (expected_authorization_audience, "expected authorization audience"),
        (expected_issuer_identity[0], "expected issuer principal"),
        (expected_issuer_identity[1], "expected issuer key"),
    ):
        _authority_identifier(value, label=label)
    _instance_identifier(
        expected_observer_identity[1],
        label="expected observer instance",
    )
    _uuid4(
        expected_issuer_identity[2],
        label="expected issuer incarnation",
    )
    validate_expected_authorization_cut(expected_authorization_cut)
    for value, label in (
        (decision.decision_kind, "decision kind"),
        (decision.observer_principal, "observer principal"),
        (decision.source_session_kind, "source session kind"),
        (decision.logical_session_id, "logical session"),
        (decision.issuer_principal, "decision issuer"),
        (decision.issuer_key_id, "decision issuer key"),
    ):
        _authority_identifier(value, label=label)
    _instance_identifier(
        decision.observer_instance,
        label="observer instance",
    )
    _uuid4(decision.decision_id, label="decision ID")
    _uuid4(decision.caller_operation_id, label="caller operation ID")
    _uuid4(decision.source_generation, label="decision source generation")
    _uuid4(
        decision.coordinator_clock_incarnation,
        label="decision coordinator clock",
    )
    _uuid4(decision.issuer_incarnation, label="decision issuer incarnation")
    for value, label in (
        (decision.caller_request_digest, "caller request digest"),
        (decision.capability_digest, "capability digest"),
        (decision.capability_seal_digest, "capability seal digest"),
        (
            decision.capability_issuer_snapshot_digest,
            "capability issuer snapshot digest",
        ),
        (decision.manifest_digest, "manifest digest"),
        (decision.manifest_entry_digest, "manifest entry digest"),
        (decision.canonical_scope_digest, "scope digest"),
        (
            decision.boundary_scope_membership_digest,
            "boundary scope membership digest",
        ),
        (decision.stable_grant_key_digest, "stable grant key digest"),
        (decision.full_boundary_key_digest, "full boundary key digest"),
        (decision.grant_digest, "grant digest"),
        (decision.server_entry_head_digest, "server entry head digest"),
        (decision.server_selector_digest, "server selector digest"),
        (decision.security_state_digest, "security state digest"),
        (decision.semantic_decision_digest, "semantic decision digest"),
        (
            decision.fixture_authentication_tag,
            "decision fixture authentication tag",
        ),
    ):
        _digest64(value, label=label, authority_bearing=True)
    _require(
        decision.authority_effect == NO_FUTURE_AUTHORITY,
        "read decision incorrectly carries future authority",
    )
    _require(
        (
            decision.issuer_principal,
            decision.issuer_key_id,
            decision.issuer_incarnation,
        )
        == expected_issuer_identity,
        "read decision claims a different issuer identity",
    )
    validate_authorization_ingress_context(
        decision.authorization_ingress_context,
        expected_observer_identity=expected_observer_identity,
        expected_authorization_audience=expected_authorization_audience,
        expected_transport_context=(
            expected_authorization_cut.authorization_endpoint_profile,
            expected_authorization_cut.authorization_connection_instance,
            expected_authorization_cut.authorization_replay_domain,
        ),
        expected_manifest_digest=expected_authorization_cut.manifest_digest,
        expected_security_state=(
            expected_authorization_cut.security_state_digest,
            expected_authorization_cut.security_epoch,
            expected_authorization_cut.revocation_epoch,
        ),
        expected_coordinator_clock_incarnation=(
            expected_authorization_cut.coordinator_clock_incarnation
        ),
        checked_at=decision.checked_at,
        fixture_key=fixture_key,
    )
    expected_kind = (
        "BOUNDED_HISTORY_RESULT"
        if scope.operation == "history_query"
        else "LIVE_SUBSCRIPTION_RELEASE"
    )
    _require(
        decision.decision_kind == expected_kind
        and (decision.observer_principal, decision.observer_instance)
        == expected_observer_identity
        and expected_authorization_audience == scope.authorization_audience
        and authorization_ingress_artifact_digest(
            decision.authorization_ingress_context
        )
        == expected_authorization_cut.authorization_ingress_artifact_digest
        and (
            decision.capability_digest,
            decision.capability_seal_digest,
            decision.capability_issuer_snapshot_digest,
            decision.manifest_digest,
            decision.manifest_entry_digest,
            decision.stable_grant_key_digest,
            decision.full_boundary_key_digest,
            decision.grant_digest,
            decision.server_entry_head_digest,
            decision.server_selector_digest,
            decision.authority_realm_key,
            decision.source_session_kind,
            decision.logical_session_id,
            decision.source_generation,
            decision.security_state_digest,
            decision.security_epoch,
            decision.revocation_epoch,
            decision.coordinator_clock_incarnation,
            decision.exclusive_not_after,
            decision.maximum_release_count,
        )
        == (
            expected_authorization_cut.capability_digest,
            expected_authorization_cut.capability_seal_digest,
            expected_authorization_cut.capability_issuer_snapshot_digest,
            expected_authorization_cut.manifest_digest,
            expected_authorization_cut.manifest_entry_digest,
            expected_authorization_cut.stable_grant_key_digest,
            expected_authorization_cut.full_boundary_key_digest,
            expected_authorization_cut.grant_digest,
            expected_authorization_cut.server_entry_head_digest,
            expected_authorization_cut.server_selector_digest,
            expected_authorization_cut.authority_realm_key,
            expected_authorization_cut.source_session_kind,
            expected_authorization_cut.logical_session_id,
            expected_authorization_cut.source_generation,
            expected_authorization_cut.security_state_digest,
            expected_authorization_cut.security_epoch,
            expected_authorization_cut.revocation_epoch,
            expected_authorization_cut.coordinator_clock_incarnation,
            expected_authorization_cut.exclusive_not_after,
            expected_authorization_cut.maximum_release_count,
        )
        and decision.caller_request_digest
        == canonical_read_request_digest(
            scope=scope,
            membership=membership,
            caller_operation_id=decision.caller_operation_id,
            expected_boundary_identity=expected_boundary_identity,
        )
        and decision.canonical_scope_digest == scope.scope_digest
        and decision.boundary_scope_membership_digest == membership.membership_digest
        and decision.authority_realm_key == scope.authority_realm_key
        and decision.source_session_kind == scope.source_session_kind
        and decision.logical_session_id == scope.logical_session_id
        and decision.source_generation == scope.source_generation,
        "read decision does not bind this exact scope/source",
    )
    _require(
        type(decision.security_epoch) is int
        and 0 < decision.security_epoch <= MAX_SAFE_INTEGER
        and type(decision.revocation_epoch) is int
        and 0 < decision.revocation_epoch <= MAX_SAFE_INTEGER
        and type(decision.checked_at) is int
        and type(decision.exclusive_not_after) is int
        and 0 <= decision.checked_at < decision.exclusive_not_after <= MAX_SAFE_INTEGER
        and type(decision.maximum_release_count) is int
        and 1 <= decision.maximum_release_count <= 4096,
        "read decision epochs, deadline, or release bound are invalid",
    )
    if scope.operation == "history_query":
        _require(
            decision.history_request_digest == canonical_history_request_digest(scope)
            and decision.maximum_release_count == 1,
            "history decision lacks this exact bounded request/result use",
        )
    else:
        _require(
            decision.history_request_digest is None,
            "subscription decision contains history authority",
        )
    _require(
        decision.semantic_decision_digest == semantic_read_decision_digest(decision)
        and hmac.compare_digest(
            decision.fixture_authentication_tag,
            _decision_tag(decision, fixture_key=fixture_key),
        ),
        "read decision semantic digest or synthetic fixture seal is invalid",
    )


_BRIDGE_DATACLASS_TYPES = (
    CanonicalObserverReadScope,
    ObserverBoundaryReadScopeMembership,
    SyntheticVerifiedAuthorizationIngressContext,
    SyntheticVerifiedReleaseRecipientContext,
    ExpectedQualifiedDeadlineMappingStateCut,
    QualifiedDecisionDeadlineMapping,
    ExpectedGrantCurrentnessStateCut,
    SyntheticAuthenticatedGrantCurrentnessEvidence,
    ObserverReadReleaseCAS,
    SyntheticValidatedObserverReadReleaseCASReceipt,
    SyntheticCommittedObserverReadOutboxArtifact,
    SyntheticObserverReadOutboxCommitReceipt,
    ExpectedCommittedObserverReadOutboxStateCut,
    ExpectedDispatchDestinationCut,
    SyntheticAuthenticatedDispatchContext,
    ExpectedObserverReadAuthorizationCut,
    SealedObserverReadAuthorizationDecision,
)
_BRIDGE_DATACLASS_TYPE_REFS.update(
    {cls: f"ncp.b01.bridge.{cls.__name__}@1" for cls in _BRIDGE_DATACLASS_TYPES}
)
_require(
    len(_BRIDGE_DATACLASS_TYPE_REFS) == len(_BRIDGE_DATACLASS_TYPES),
    "bridge stable dataclass type references are not one-to-one",
)
_BRIDGE_DATACLASS_TYPE_REFS = FrozenTypeRegistry(
    tuple(_BRIDGE_DATACLASS_TYPE_REFS.items())
)


def artifact_shape_digest() -> str:
    """Return one deterministic digest for the shared canonical type shapes."""

    shape = {
        stable_id: list(field_names)
        for stable_id, field_names in (
            _BRIDGE_DATACLASS_TYPE_REFS.revalidated_shape_view()
        )
    }
    return _owned_json_domain_digest("ncp.b01.bridge.ArtifactShapeSet@1", shape)


_BRIDGE_COMMITMENT_SUITE_DOMAIN = "ncp.b01.bridge.CanonicalCommitmentSuite@1"
_BRIDGE_REFERENCE_DOMAIN = "ncp.b01.bridge.ReferenceVector@1"
_BRIDGE_REFERENCE_OUTPUT_HEX = {
    "artifact": (
        "7b22246272696467655f6b696e64223a226172746966616374222c226669656c"
        "6473223a5b5b22626f756e646172795f73746174655f686561645f6469676573"
        "74222c2261225d2c5b226772616e745f656e7472795f686561645f6469676573"
        "74222c2262225d2c5b2273746174655f76657273696f6e222c315d2c5b227072"
        "696f725f72656c656173655f636f756e74222c305d2c5b226772616e745f6375"
        "7272656e746e6573735f726563656970745f646967657374222c2263225d2c5b"
        "226c6f63616c5f6772616e745f6578636c75736976655f6e6f745f6166746572"
        "222c325d2c5b2265766964656e63655f61727469666163745f64696765737422"
        "2c2264225d5d2c22747970655f726566223a226e63702e6230312e6272696467"
        "652e45787065637465644772616e7443757272656e746e657373537461746543"
        "75744031227d"
    ),
    "bytes": (
        "7b22246272696467655f6b696e64223a22696d6d757461626c655f6279746573"
        "222c22686578223a2230306666227d"
    ),
    "false": "66616c7365",
    "list": (
        "7b22246272696467655f6b696e64223a226c697374222c226974656d73223a5b2278222c315d7d"
    ),
    "mapping": (
        "7b22246272696467655f6b696e64223a226d617070696e67222c22656e747269"
        "6573223a5b5b2261222c315d2c5b22ceb2222c325d5d7d"
    ),
    "max_int": "39303037313939323534373430393931",
    "min_int": "2d39303037313939323534373430393931",
    "null": "6e756c6c",
    "true": "74727565",
    "tuple": (
        "7b22246272696467655f6b696e64223a227475706c65222c226974656d73223a"
        "5b2278222c315d7d"
    ),
    "unicode": "22412fc3a95c6e22",
    "unicode_escape_and_normalization": (
        "225c225c5c5c625c745c6e5c665c725c7530303031e280a8e280a9f09f9982c3a92f65cc8122"
    ),
    "unicode_scalar_order": (
        "7b22246272696467655f6b696e64223a226d617070696e67222c22656e747269"
        "6573223a5b5b22ee8080222c22424d505f505249564154455f555345225d2c5b"
        "22f0908080222c2241535452414c5f504c414e455f4f4e45225d5d7d"
    ),
}
_BRIDGE_REFERENCE_FRAME_HEX = (
    "4e43502d4230312d4f425345525645522d524541442d434150545552452d4252"
    "494447452d5631006e63702e6230312e6272696467652e5265666572656e6365"
    "566563746f724031007b22246272696467655f6b696e64223a226d617070696e"
    "67222c22656e7472696573223a5b5b2261222c315d5d7d"
)
_BRIDGE_REFERENCE_FRAME_DIGEST = (
    "fc2967e5ecbbddf0ef55a43c67fe0a6823c796a7558d6b0f1fbb76e8a097003f"
)


def _bridge_reference_inputs() -> dict[str, Any]:
    return {
        "artifact": ExpectedGrantCurrentnessStateCut(
            boundary_state_head_digest="a",
            grant_entry_head_digest="b",
            state_version=1,
            prior_release_count=0,
            grant_currentness_receipt_digest="c",
            local_grant_exclusive_not_after=2,
            evidence_artifact_digest="d",
        ),
        "bytes": b"\x00\xff",
        "false": False,
        "list": FrozenList(("x", 1)),
        "mapping": FrozenMap((("a", 1), ("β", 2))),
        "max_int": MAX_SAFE_INTEGER,
        "min_int": -MAX_SAFE_INTEGER,
        "null": None,
        "true": True,
        "tuple": ("x", 1),
        "unicode": "A/é\n",
        "unicode_escape_and_normalization": (
            '"\\\b\t\n\f\r\x01\u2028\u2029\U0001f642é/e\u0301'
        ),
        "unicode_scalar_order": FrozenMap(
            (
                ("\ue000", "BMP_PRIVATE_USE"),
                ("\U00010000", "ASTRAL_PLANE_ONE"),
            )
        ),
    }


def _build_bridge_commitment_suite() -> dict[str, Any]:
    reference_input_descriptions = {
        "artifact": {
            "field_values_in_declared_order": [
                ["boundary_state_head_digest", "a"],
                ["grant_entry_head_digest", "b"],
                ["state_version", 1],
                ["prior_release_count", 0],
                ["grant_currentness_receipt_digest", "c"],
                ["local_grant_exclusive_not_after", 2],
                ["evidence_artifact_digest", "d"],
            ],
            "input_kind": "EXACT_REGISTERED_ARTIFACT",
            "type_ref": ("ncp.b01.bridge.ExpectedGrantCurrentnessStateCut@1"),
        },
        "bytes": {
            "input_kind": "EXACT_IMMUTABLE_BYTES",
            "input_octets_hex": "00ff",
        },
        "false": {"input_kind": "EXACT_BOOLEAN", "value": False},
        "list": {
            "input_kind": "EXACT_FROZEN_LIST_WITH_EXACT_TUPLE_BACKING",
            "items": ["x", 1],
        },
        "mapping": {
            "input_kind": ("EXACT_FROZEN_MAP_SORTED_UNIQUE_UNICODE_SCALAR_STRING_KEYS"),
            "input_entries_in_canonical_order": [["0061", 1], ["03b2", 2]],
        },
        "max_int": {
            "input_kind": "EXACT_INTEGER",
            "value": MAX_SAFE_INTEGER,
        },
        "min_int": {
            "input_kind": "EXACT_INTEGER",
            "value": -MAX_SAFE_INTEGER,
        },
        "null": {"input_kind": "NULL", "value": None},
        "true": {"input_kind": "EXACT_BOOLEAN", "value": True},
        "tuple": {
            "input_kind": "EXACT_TUPLE",
            "items": ["x", 1],
        },
        "unicode": {
            "input_kind": "EXACT_UNICODE_SCALAR_STRING",
            "unicode_code_points_hex": ["0041", "002f", "00e9", "000a"],
        },
        "unicode_escape_and_normalization": {
            "input_kind": "EXACT_UNICODE_SCALAR_STRING",
            "unicode_code_points_hex": [
                "0022",
                "005c",
                "0008",
                "0009",
                "000a",
                "000c",
                "000d",
                "0001",
                "2028",
                "2029",
                "01f642",
                "00e9",
                "002f",
                "0065",
                "0301",
            ],
            "verifies": [
                "QUOTATION_MARK_AND_BACKSLASH_ESCAPES",
                "ALL_FIVE_SHORT_CONTROL_ESCAPES",
                "LOWERCASE_U00XX_ESCAPE_FOR_ANOTHER_CONTROL",
                "UNESCAPED_U2028_AND_U2029_UTF8",
                "UNESCAPED_ASTRAL_UTF8",
                "NO_COMPOSED_OR_DECOMPOSED_UNICODE_NORMALIZATION",
            ],
        },
        "unicode_scalar_order": {
            "input_entries_in_canonical_order": [
                ["e000", "BMP_PRIVATE_USE"],
                ["010000", "ASTRAL_PLANE_ONE"],
            ],
            "input_kind": ("EXACT_FROZEN_MAP_SORTED_UNIQUE_UNICODE_SCALAR_STRING_KEYS"),
            "ordering_discriminator": (
                "U+E000_PRECEDES_U+10000_BY_UNICODE_SCALAR_SEQUENCE"
            ),
        },
    }
    reference_vectors = [
        {
            "canonical_utf8_hex": _BRIDGE_REFERENCE_OUTPUT_HEX[name],
            "input": reference_input_descriptions[name],
            "name": name,
        }
        for name in sorted(_BRIDGE_REFERENCE_OUTPUT_HEX)
    ]
    return {
        "canonical_json": {
            "allow_nan": False,
            "encoding": "UTF-8_STRICT",
            "ensure_ascii": False,
            "integer_rendering": "BASE_10_MINIMAL_NO_PLUS_NO_LEADING_ZERO",
            "json_literals": {
                "false": "false",
                "null": "null",
                "true": "true",
            },
            "object_member_order": "ASCENDING_UNICODE_SCALAR_SEQUENCE",
            "separators": {
                "item": ",",
                "key_value": ":",
            },
            "sort_keys": True,
            "string_escaping": {
                "backslash": "\\\\",
                "control_short_escapes": {
                    "U+0008": "\\b",
                    "U+0009": "\\t",
                    "U+000A": "\\n",
                    "U+000C": "\\f",
                    "U+000D": "\\r",
                },
                "other_u0000_through_u001f": ("LOWERCASE_HEX_BACKSLASH_U00XX"),
                "quotation_mark": '\\"',
                "solidus": "UNESCAPED",
                "u2028_and_u2029": "UNESCAPED_UTF8",
            },
            "trailing_newline": False,
            "unicode_normalization": "NONE",
            "whitespace_outside_strings": "NONE",
        },
        "claim_boundary": (
            "SYNTHETIC_PRE_RATIFICATION_NON_NORMATIVE_NOT_WIRE_"
            "INTEROPERABILITY_CRYPTOGRAPHIC_QUALIFICATION_OR_RELEASE_EVIDENCE"
        ),
        "domain_digest": {
            "algorithm": "SHA-256",
            "domain": {
                "encoding": "ASCII_STRICT",
                "exact_runtime_type": "str",
                "maximum_octets": MAX_BRIDGE_DOMAIN_OCTETS,
                "regular_expression": BRIDGE_DIGEST_DOMAIN.pattern,
                "version_suffix": "@1",
            },
            "frame_components_in_order": [
                {
                    "encoding": "LITERAL_OCTETS",
                    "hex": BRIDGE_DIGEST_PREFIX.hex(),
                    "name": "protocol_prefix",
                    "octet_length": len(BRIDGE_DIGEST_PREFIX),
                },
                {
                    "encoding": "LITERAL_OCTETS",
                    "hex": BRIDGE_FRAME_SEPARATOR.hex(),
                    "name": "prefix_domain_separator",
                    "octet_length": len(BRIDGE_FRAME_SEPARATOR),
                },
                {
                    "encoding": "ASCII_STRICT",
                    "name": "domain",
                },
                {
                    "encoding": "LITERAL_OCTETS",
                    "hex": BRIDGE_FRAME_SEPARATOR.hex(),
                    "name": "domain_value_separator",
                    "octet_length": len(BRIDGE_FRAME_SEPARATOR),
                },
                {
                    "encoding": "CANONICAL_JSON_UTF8",
                    "name": "normalized_value",
                },
            ],
            "length_prefixes": "NONE",
            "output": {
                "alphabet": "LOWERCASE_HEXADECIMAL",
                "octet_length_before_hex": 32,
                "text_length": 64,
            },
            "reference_vector": {
                "canonical_input": {
                    "input_kind": "EXACT_FROZEN_MAP",
                    "input_entries": [["a", 1]],
                },
                "domain": _BRIDGE_REFERENCE_DOMAIN,
                "frame_hex": _BRIDGE_REFERENCE_FRAME_HEX,
                "sha256_lower_hex": _BRIDGE_REFERENCE_FRAME_DIGEST,
            },
        },
        "normalization": {
            "artifact": {
                "accepted_input": (
                    "EXACT_REGISTERED_FROZEN_DATACLASS_INSTANCE_NO_SUBCLASS"
                ),
                "envelope": {
                    "$bridge_kind": "artifact",
                    "fields": (
                        "ARRAY_OF_TWO_ELEMENT_FIELD_NAME_AND_NORMALIZED_VALUE_ARRAYS"
                    ),
                    "type_ref": "CLOSED_STABLE_TYPE_REFERENCE",
                },
                "field_name_encoding": "EXACT_DECLARED_IDENTIFIER_STRING",
                "field_order": "DATACLASS_DECLARATION_ORDER",
                "maximum_fields": MAX_BRIDGE_ARTIFACT_FIELDS,
                "type_registry": "EXACT_CLOSED_SUITE_TYPE_REGISTRY",
            },
            "bytes": {
                "accepted_input": "EXACT_IMMUTABLE_BYTES_NO_SUBCLASS",
                "envelope": {
                    "$bridge_kind": "immutable_bytes",
                    "hex": "TWO_LOWERCASE_HEX_DIGITS_PER_INPUT_OCTET",
                },
                "maximum_input_octets": MAX_BRIDGE_PAYLOAD_OCTETS,
                "minimum_input_octets": 1,
            },
            "alias_and_cycle_policy": {
                "immutable_dag_alias": "ACCEPT",
                "immutable_reference_cycle": "REJECT",
                "mutable_alias_during_private_freeze": "REJECT_BY_DEFAULT",
                "mutable_reference_cycle": "REJECT",
            },
            "dispatch_order": [
                "EXACT_FROZEN_MAP",
                "EXACT_FROZEN_LIST",
                "EXACT_TUPLE",
                "REJECT_EXACT_OR_SUBCLASSED_MUTABLE_DICT_OR_LIST",
                "EXACT_REGISTERED_DATACLASS_INSTANCE",
                "NULL",
                "EXACT_BOOL",
                "EXACT_PORTABLE_INTEGER",
                "EXACT_NONEMPTY_IMMUTABLE_BYTES",
                "EXACT_UNICODE_SCALAR_STRING",
                "REJECT",
            ],
            "input_node_accounting": {
                "artifact_field_names_count_as_nodes": False,
                "collection_or_artifact_root_counts_as_one": True,
                "mapping_keys_count_as_nodes": False,
                "maximum_nodes_including_root": MAX_BRIDGE_CANONICAL_NODES,
                "nested_values_each_count_as_one": True,
                "synthetic_typed_profile_wrappers_count_as_nodes": False,
            },
            "limits": {
                "maximum_aggregate_scalar_utf8_and_payload_octets": (
                    MAX_BRIDGE_CANONICAL_OCTETS
                ),
                "maximum_artifact_fields": MAX_BRIDGE_ARTIFACT_FIELDS,
                "maximum_canonical_output_octets": (MAX_BRIDGE_CANONICAL_OCTETS),
                "maximum_collection_items_or_mapping_entries": (
                    MAX_BRIDGE_COLLECTION_ITEMS
                ),
                "maximum_depth_inclusive": MAX_BRIDGE_CANONICAL_DEPTH,
                "maximum_immutable_payload_octets": MAX_BRIDGE_PAYLOAD_OCTETS,
                "maximum_input_nodes": MAX_BRIDGE_CANONICAL_NODES,
                "maximum_utf8_octets_per_string_or_mapping_key": (
                    MAX_BRIDGE_STRING_OCTETS
                ),
                "root_depth": 0,
            },
            "list": {
                "accepted_input": (
                    "EXACT_FROZEN_LIST_WITH_EXACT_TUPLE_BACKING_NO_SUBCLASS"
                ),
                "envelope": {
                    "$bridge_kind": "list",
                    "items": "NORMALIZED_VALUES_IN_INPUT_ORDER",
                },
            },
            "mapping": {
                "accepted_input": (
                    "EXACT_FROZEN_MAP_WITH_EXACT_TUPLE_OF_EXACT_TWO_TUPLES"
                ),
                "duplicate_key_policy": "REJECT",
                "envelope": {
                    "$bridge_kind": "mapping",
                    "entries": ("ARRAY_OF_TWO_ELEMENT_KEY_AND_NORMALIZED_VALUE_ARRAYS"),
                },
                "key_order": "ASCENDING_UNICODE_SCALAR_SEQUENCE",
                "keys": "EXACT_UNICODE_SCALAR_STRINGS_NO_SUBCLASS",
                "snapshot_before_emit": (
                    "KEY_VALUE_AND_BOUNDED_KEY_LENGTH_SNAPSHOTTED_ONCE"
                ),
                "unicode_normalization": "NONE",
            },
            "private_owned_authoring_conversion": {
                "accepted_mutable_roots": "EXACT_DICT_OR_EXACT_LIST_ONLY",
                "caller_obligation": (
                    "EXCLUSIVE_UNPUBLISHED_OWNERSHIP_NO_CONCURRENT_MUTATION"
                ),
                "dataclass_policy": (
                    "ONLY_EXACT_FROZEN_CLASSES_IN_THE_CLOSED_TYPE_REGISTRY"
                ),
                "result": (
                    "STRUCTURALLY_IMMUTABLE_FROZEN_MAP_OR_FROZEN_LIST_GRAPH_"
                    "WITH_REGISTERED_ARTIFACT_STABILITY_AS_A_CALLER_OBLIGATION"
                ),
                "shared_mutable_policy": "REJECT_BY_DEFAULT",
                "synchronization_guarantee": "NONE",
            },
            "resource_failure_behavior": {
                "hex_encoding": "BOUNDED_CHUNKED_LOWERCASE_HEX",
                "normalized_object_tree_allocation": "NONE",
                "partial_output_on_failure": "CLEARED",
                "per_chunk_or_scalar_bound_check_before_allocation": True,
                "string_utf8_and_json_lengths": "CHECKED_BEFORE_JSON_ENCODER_CALL",
                "whole_graph_preflight": False,
            },
            "scalar_domains": {
                "boolean": {
                    "accepted_input": "EXACT_BOOL",
                    "outputs": {
                        "false": False,
                        "true": True,
                    },
                },
                "integer": {
                    "accepted_input": "EXACT_INT_NO_BOOL_NO_SUBCLASS",
                    "maximum_inclusive": MAX_SAFE_INTEGER,
                    "minimum_inclusive": -MAX_SAFE_INTEGER,
                },
                "null": {
                    "accepted_input": "EXACT_SINGLETON_NONE",
                    "output": None,
                },
                "string": {
                    "accepted_input": (
                        "EXACT_STR_OF_UNICODE_SCALAR_VALUES_NO_SUBCLASS"
                    ),
                    "empty_allowed": True,
                    "unicode_normalization": "NONE",
                },
            },
            "tuple": {
                "accepted_input": "EXACT_TUPLE_NO_SUBCLASS",
                "envelope": {
                    "$bridge_kind": "tuple",
                    "items": "NORMALIZED_VALUES_IN_INPUT_ORDER",
                },
            },
            "unsupported_input": (
                "REJECT_MUTABLE_DICT_LIST_FLOAT_COMPLEX_DECIMAL_ENUM_SET_"
                "FROZENSET_BYTEARRAY_MEMORYVIEW_CLASS_UNREGISTERED_OR_NONFROZEN_"
                "DATACLASS_SUBCLASSES_AND_ALL_OTHER_TYPES"
            ),
            "type_registry": {
                "accepted_container": "EXACT_DICT_OR_FROZEN_TYPE_REGISTRY",
                "class_identity": "EXACT_PLAIN_METACLASS_TYPE_IDENTITY",
                "duplicate_class_or_stable_id": "REJECT",
                "same_process_integrity_boundary": {
                    "artifact_instance_state": (
                        "CALLER_MUST_KEEP_STABLE_THROUGH_CALL_RETURN"
                    ),
                    "artifact_snapshot": (
                        "REVALIDATE_EACH_REACHED_CLASS_BEFORE_ITS_FIRST_INSTANCE_"
                        "PER_PUBLIC_TRAVERSAL_THEN_READ_EACH_INSTANCE_FIELD_ONCE_"
                        "THROUGH_OBJECT_GETATTRIBUTE"
                    ),
                    "error_construction": (
                        "EXACT_EXCEPTION_CLASS_WITH_NO_CALLER_DEFINED_NEW_OR_INIT"
                    ),
                    "field_metadata": (
                        "EXACT_SHARED_EMPTY_METADATA_SENTINEL_WITH_NO_CALLER_"
                        "MAPPING_DISPATCH"
                    ),
                    "frozen_mutator_guard": (
                        "STRUCTURAL_GENERATED_CODE_EQUIVALENCE_WITH_EXACT_"
                        "CANDIDATE_CLASS_AND_FROZEN_INSTANCE_ERROR_CLOSURE_"
                        "AND_PINNED_FUNCTION_CODE_GLOBALS_BUILTINS_STATE"
                    ),
                    "canonicalizer_and_interpreter_code_integrity": (
                        "CALLER_MUST_PRESERVE_THROUGH_CALL_RETURN"
                    ),
                    "concurrent_integrity_mutation": (
                        "CALLER_MUST_PREVENT_CLASS_INSTANCE_REGISTRY_OR_WRAPPER_"
                        "BACKING_MUTATION_THROUGH_CALL_RETURN"
                    ),
                    "non_slot_instance_state": (
                        "EXACT_NATIVE_DICT_WITH_KEYS_EXACTLY_EQUAL_TO_PINNED_"
                        "FIELD_NAMES"
                    ),
                    "registration_pins": (
                        "DIRECT_OBJECT_FROZEN_DATACLASS_PARAMETERS_FIELDS_CLASS_"
                        "BINDINGS_AND_GENERATED_MUTATOR_STATE"
                    ),
                    "registry_snapshot": (
                        "EXACT_TUPLE_BACKING_GLOBAL_IDENTITY_ALIGNMENT_BOUNDS_"
                        "AND_DUPLICATE_REJECTION_BEFORE_TARGETED_ARTIFACT_READ"
                    ),
                    "registered_class_shape": (
                        "FROZEN_REGISTRY_PINNED_AT_REGISTRATION_EACH_REACHED_CLASS_"
                        "REVALIDATED_BEFORE_ITS_FIRST_INSTANCE_PER_PUBLIC_TRAVERSAL_"
                        "CALLER_MUST_PREVENT_CONCURRENT_MUTATION_THROUGH_CALL_RETURN"
                    ),
                    "scope": (
                        "SAME_PROCESS_INTEGRITY_EVIDENCE_ONLY_NOT_ATOMIC_"
                        "SNAPSHOT_OR_ADVERSARIAL_IN_PROCESS_SANDBOX"
                    ),
                    "structural_container_backing": (
                        "FROZEN_MAP_AND_FROZEN_LIST_BACKING_READ_ONCE_AND_CALLER_"
                        "STABLE_THROUGH_CALL_RETURN"
                    ),
                },
                "stable_id": "NONEMPTY_EXACT_STRING_WITH_AGGREGATE_BYTE_CAP",
                "snapshot_lookup_key": "IN_PROCESS_EXACT_TYPE_OBJECT_ID",
            },
        },
        "reference_vectors": reference_vectors,
        "schema": "ncp.b01.bridge-canonical-commitment-suite.v1",
        "type_registry": [
            {
                "field_order": list(field_names),
                "type_ref": stable_id,
            }
            for stable_id, field_names in sorted(
                _BRIDGE_DATACLASS_TYPE_REFS.revalidated_shape_view(),
                key=lambda item: item[0],
            )
        ],
    }


def _validate_printable_ascii_safe_json(
    value: Any,
    *,
    label: str,
) -> None:
    """Apply bounded JSON preflight before embedded-profile semantic work."""

    stack: list[tuple[Any, str, int]] = [(value, label, 0)]
    seen_container_ids: set[int] = set()
    remaining_nodes = MAX_BRIDGE_CANONICAL_NODES
    canonical_octets = 0

    def add_canonical_octets(count: int) -> None:
        nonlocal canonical_octets
        canonical_octets += count
        _require(
            canonical_octets <= MAX_BRIDGE_CANONICAL_OCTETS,
            f"{label} exceeds the pre-semantic canonical-octet limit",
        )

    def printable_ascii_string_octets(item: Any, *, item_label: str) -> int:
        _require(type(item) is str, f"{item_label} type is not exact")
        _require(
            len(item) <= MAX_BRIDGE_STRING_OCTETS,
            f"{item_label} exceeds the pre-semantic string-octet limit",
        )
        _require(
            all(0x20 <= ord(character) <= 0x7E for character in item),
            f"{item_label} contains a non-printable-ASCII string",
        )
        return 2 + sum(2 if character in {'"', "\\"} else 1 for character in item)

    while stack:
        item, item_label, depth = stack.pop()
        _require(
            depth <= MAX_BRIDGE_CANONICAL_DEPTH,
            f"{item_label} exceeds the root-depth-0 pre-semantic limit",
        )
        remaining_nodes -= 1
        _require(
            remaining_nodes >= 0,
            f"{label} exceeds the pre-semantic input-node limit",
        )
        if type(item) is dict:
            identity = id(item)
            _require(
                identity not in seen_container_ids,
                f"{item_label} contains a shared or cyclic mapping",
            )
            seen_container_ids.add(identity)
            _require(
                len(item) <= MAX_BRIDGE_COLLECTION_ITEMS,
                f"{item_label} exceeds the pre-semantic mapping-entry limit",
            )
            add_canonical_octets(2 + max(0, len(item) - 1) + len(item))
            for key, child in item.items():
                _require(
                    type(key) is str and bool(key),
                    f"{item_label} contains a non-printable-ASCII mapping key",
                )
                add_canonical_octets(
                    printable_ascii_string_octets(
                        key,
                        item_label=f"{item_label} mapping key",
                    )
                )
                stack.append((child, f"{item_label}.{key}", depth + 1))
            continue
        if type(item) is list:
            identity = id(item)
            _require(
                identity not in seen_container_ids,
                f"{item_label} contains a shared or cyclic list",
            )
            seen_container_ids.add(identity)
            _require(
                len(item) <= MAX_BRIDGE_COLLECTION_ITEMS,
                f"{item_label} exceeds the pre-semantic list-item limit",
            )
            add_canonical_octets(2 + max(0, len(item) - 1))
            for index in range(len(item) - 1, -1, -1):
                stack.append((item[index], f"{item_label}[{index}]", depth + 1))
            continue
        if type(item) is str:
            add_canonical_octets(
                printable_ascii_string_octets(item, item_label=item_label)
            )
            continue
        if type(item) is int:
            _require(
                -MAX_SAFE_INTEGER <= item <= MAX_SAFE_INTEGER,
                f"{item_label} integer is outside the portable safe range",
            )
            add_canonical_octets(len(str(item)))
            continue
        if item is None:
            add_canonical_octets(4)
            continue
        if type(item) is bool:
            add_canonical_octets(4 if item else 5)
            continue
        raise BridgeValidationError(f"{item_label} contains a non-JSON scalar")


_BRIDGE_COMMITMENT_SUITE_VALUE = _build_bridge_commitment_suite()
_BRIDGE_COMMITMENT_SUITE_KEYS = frozenset(_BRIDGE_COMMITMENT_SUITE_VALUE)
_validate_printable_ascii_safe_json(
    _BRIDGE_COMMITMENT_SUITE_VALUE,
    label="bridge commitment suite",
)
_BRIDGE_COMMITMENT_SUITE_JSON = json.dumps(
    _BRIDGE_COMMITMENT_SUITE_VALUE,
    allow_nan=False,
    ensure_ascii=False,
    separators=(",", ":"),
    sort_keys=True,
).encode("utf-8")
del _BRIDGE_COMMITMENT_SUITE_VALUE
_BRIDGE_COMMITMENT_SUITE_CANONICAL_BYTES = _canonical_bytes(
    _freeze_owned_bridge_json(json.loads(_BRIDGE_COMMITMENT_SUITE_JSON))
)
_BRIDGE_COMMITMENT_SUITE_COMPUTED_DIGEST = _owned_json_domain_digest(
    _BRIDGE_COMMITMENT_SUITE_DOMAIN,
    json.loads(_BRIDGE_COMMITMENT_SUITE_JSON),
)
_BRIDGE_COMMITMENT_SUITE_EXPECTED_DIGEST = (
    "92b1843fefd907cf30a1cfceb7fa251e2eb1ba46f3f47a68af4dfcf8d7608cf9"
)
_require(
    hmac.compare_digest(
        _BRIDGE_COMMITMENT_SUITE_COMPUTED_DIGEST,
        _BRIDGE_COMMITMENT_SUITE_EXPECTED_DIGEST,
    ),
    "bridge commitment suite differs from its frozen known-answer digest",
)
_BRIDGE_COMMITMENT_SUITE_DIGEST = _BRIDGE_COMMITMENT_SUITE_EXPECTED_DIGEST


def bridge_commitment_suite() -> dict[str, Any]:
    """Return an isolated machine-readable copy of the closed commitment suite."""

    suite = json.loads(_BRIDGE_COMMITMENT_SUITE_JSON)
    _require(type(suite) is dict, "bridge commitment suite root is not a mapping")
    _validate_printable_ascii_safe_json(
        suite,
        label="bridge commitment suite copy",
    )
    return suite


def bridge_commitment_suite_digest() -> str:
    """Return the domain-separated digest of the exact commitment suite."""

    return _BRIDGE_COMMITMENT_SUITE_DIGEST


def bridge_commitment_suite_digest_domain() -> str:
    """Return the one public domain that frames the exact suite digest."""

    return _BRIDGE_COMMITMENT_SUITE_DOMAIN


def validate_bridge_commitment_suite(
    suite: Any,
    *,
    expected_suite_digest_domain: str,
    expected_suite_digest: str,
) -> None:
    """Require the exact closed suite and independently supplied digest frame."""

    _require(type(suite) is dict, "bridge commitment suite type is not exact")
    _require(
        len(suite) == len(_BRIDGE_COMMITMENT_SUITE_KEYS)
        and frozenset(suite) == _BRIDGE_COMMITMENT_SUITE_KEYS,
        "bridge commitment suite root key set is not exact",
    )
    _validate_printable_ascii_safe_json(
        suite,
        label="supplied bridge commitment suite",
    )
    _require(
        type(expected_suite_digest_domain) is str
        and hmac.compare_digest(
            expected_suite_digest_domain,
            _BRIDGE_COMMITMENT_SUITE_DOMAIN,
        ),
        "bridge commitment suite digest domain differs",
    )
    _digest64(
        expected_suite_digest,
        label="expected bridge commitment suite digest",
        authority_bearing=True,
    )
    _require(
        hmac.compare_digest(
            json.dumps(
                suite,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8"),
            _BRIDGE_COMMITMENT_SUITE_JSON,
        )
        and hmac.compare_digest(
            expected_suite_digest,
            _BRIDGE_COMMITMENT_SUITE_DIGEST,
        )
        and bool(_BRIDGE_COMMITMENT_SUITE_CANONICAL_BYTES),
        "bridge commitment suite or retained suite digest differs",
    )


def _suite_leaf_paths(
    value: Any,
    path: tuple[str | int, ...] = (),
) -> tuple[tuple[str | int, ...], ...]:
    if type(value) is dict:
        return tuple(
            leaf
            for key in sorted(value)
            for leaf in _suite_leaf_paths(value[key], (*path, key))
        )
    if type(value) is list:
        return tuple(
            leaf
            for index, item in enumerate(value)
            for leaf in _suite_leaf_paths(item, (*path, index))
        )
    return (path,)


def _suite_list_paths(
    value: Any,
    path: tuple[str | int, ...] = (),
) -> tuple[tuple[str | int, ...], ...]:
    own = (path,) if type(value) is list and len(value) > 1 else ()
    if type(value) is dict:
        return own + tuple(
            nested
            for key in sorted(value)
            for nested in _suite_list_paths(value[key], (*path, key))
        )
    if type(value) is list:
        return own + tuple(
            nested
            for index, item in enumerate(value)
            for nested in _suite_list_paths(item, (*path, index))
        )
    return own


def _suite_path_parent(
    value: dict[str, Any],
    path: tuple[str | int, ...],
) -> tuple[Any, str | int]:
    _require(bool(path), "bridge suite mutation path is empty")
    parent: Any = value
    for component in path[:-1]:
        parent = parent[component]
    return parent, path[-1]


def _mutated_suite_leaf(value: Any) -> Any:
    if value is None:
        return "MUTATED_NULL"
    if type(value) is bool:
        return not value
    if type(value) is int:
        return value - 1 if value == MAX_SAFE_INTEGER else value + 1
    if type(value) is str:
        return value + "#MUTATED"
    raise BridgeValidationError("bridge suite contains an unsupported leaf")


def bridge_commitment_suite_mutation_report() -> dict[str, Any]:
    """Mutate every declared leaf and every ordered list, and require rejection."""

    suite = bridge_commitment_suite()
    validate_bridge_commitment_suite(
        suite,
        expected_suite_digest_domain=bridge_commitment_suite_digest_domain(),
        expected_suite_digest=bridge_commitment_suite_digest(),
    )
    category_leaf_counts: dict[str, int] = {}
    leaf_rejections = 0
    for path in _suite_leaf_paths(suite):
        mutant = bridge_commitment_suite()
        parent, component = _suite_path_parent(mutant, path)
        parent[component] = _mutated_suite_leaf(parent[component])
        mutant_digest = _owned_json_domain_digest(
            _BRIDGE_COMMITMENT_SUITE_DOMAIN, mutant
        )
        try:
            validate_bridge_commitment_suite(
                mutant,
                expected_suite_digest_domain=bridge_commitment_suite_digest_domain(),
                expected_suite_digest=mutant_digest,
            )
        except BridgeValidationError:
            leaf_rejections += 1
            category = str(path[0])
            category_leaf_counts[category] = category_leaf_counts.get(category, 0) + 1
        else:
            raise BridgeValidationError(
                "self-consistent bridge suite leaf mutation was accepted"
            )

    sequence_order_rejections = 0
    for path in _suite_list_paths(suite):
        mutant = bridge_commitment_suite()
        parent, component = _suite_path_parent(mutant, path)
        sequence = parent[component]
        swap_index = next(
            (
                index
                for index in range(1, len(sequence))
                if sequence[index] != sequence[0]
            ),
            None,
        )
        if swap_index is None:
            continue
        sequence[0], sequence[swap_index] = (
            sequence[swap_index],
            sequence[0],
        )
        mutant_digest = _owned_json_domain_digest(
            _BRIDGE_COMMITMENT_SUITE_DOMAIN, mutant
        )
        try:
            validate_bridge_commitment_suite(
                mutant,
                expected_suite_digest_domain=bridge_commitment_suite_digest_domain(),
                expected_suite_digest=mutant_digest,
            )
        except BridgeValidationError:
            sequence_order_rejections += 1
        else:
            raise BridgeValidationError(
                "self-consistent bridge suite sequence reorder was accepted"
            )

    top_level_removal_rejections = 0
    for key in sorted(suite):
        mutant = bridge_commitment_suite()
        del mutant[key]
        mutant_digest = _owned_json_domain_digest(
            _BRIDGE_COMMITMENT_SUITE_DOMAIN, mutant
        )
        try:
            validate_bridge_commitment_suite(
                mutant,
                expected_suite_digest_domain=bridge_commitment_suite_digest_domain(),
                expected_suite_digest=mutant_digest,
            )
        except BridgeValidationError:
            top_level_removal_rejections += 1
        else:
            raise BridgeValidationError(
                "self-consistent incomplete bridge suite was accepted"
            )

    unknown_member_mutant = bridge_commitment_suite()
    unknown_member_mutant["unknown_extension"] = "MUST_REJECT"
    try:
        validate_bridge_commitment_suite(
            unknown_member_mutant,
            expected_suite_digest_domain=bridge_commitment_suite_digest_domain(),
            expected_suite_digest=_owned_json_domain_digest(
                _BRIDGE_COMMITMENT_SUITE_DOMAIN,
                unknown_member_mutant,
            ),
        )
    except BridgeValidationError:
        unknown_member_rejections = 1
    else:
        raise BridgeValidationError("unknown bridge suite member was accepted")

    try:
        validate_bridge_commitment_suite(
            suite,
            expected_suite_digest_domain=bridge_commitment_suite_digest_domain(),
            expected_suite_digest="0" * 64,
        )
    except BridgeValidationError:
        digest_substitution_rejections = 1
    else:
        raise BridgeValidationError("bridge suite digest substitution was accepted")

    total_mutations = (
        len(_suite_leaf_paths(suite))
        + sequence_order_rejections
        + len(suite)
        + unknown_member_rejections
        + digest_substitution_rejections
    )
    total_rejections = (
        leaf_rejections
        + sequence_order_rejections
        + top_level_removal_rejections
        + unknown_member_rejections
        + digest_substitution_rejections
    )
    _require(
        total_mutations == total_rejections,
        "bridge suite mutation and rejection counts differ",
    )
    return {
        "category_leaf_mutations_rejected": {
            key: category_leaf_counts[key] for key in sorted(category_leaf_counts)
        },
        "digest_substitution_mutations_rejected": (digest_substitution_rejections),
        "leaf_mutations_rejected": leaf_rejections,
        "sequence_order_mutations_rejected": sequence_order_rejections,
        "top_level_removal_mutations_rejected": (top_level_removal_rejections),
        "total_mutations_executed": total_mutations,
        "total_mutations_rejected": total_rejections,
        "unknown_member_mutations_rejected": unknown_member_rejections,
    }


_OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_DOMAIN = (
    "ncp.b01.bridge.ObserverReadCaptureBridgeProfileV2@1"
)
_OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_BASE_KEYS = frozenset(
    {
        "authority_chain",
        "authorization",
        "canonical_type_system",
        "claim_boundary",
        "commit",
        "currentness",
        "deadline_and_clock",
        "delivery_admission",
        "dispatch",
        "exact_type_refs",
        "release_cas",
        "route_classes",
        "schema",
        "semantic_extraction",
        "synthetic_bridge_type_refs",
        "unknown_default_missing_duplicate_or_substituted",
    }
)
_OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_KEYS = frozenset(
    {
        *_OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_BASE_KEYS,
        "canonical_commitment",
    }
)
_OBSERVER_READ_CAPTURE_BRIDGE_AUTHORITY_CHAIN = [
    "LIVE_READ_CAPABILITY",
    "VERIFIED_AUTHORIZATION_INGRESS_CONTEXT",
    "SEALED_NONAUTHORIZING_READ_DECISION",
    "QUALIFIED_CONSERVATIVE_DEADLINE_MAPPING",
    "VERIFIED_GRANT_CURRENTNESS_STATE_CUT",
    "VERIFIED_RELEASE_RECIPIENT_CONTEXT",
    "VALIDATED_RELEASE_COUNTER_CAS_CANDIDATE",
    "VALIDATED_RELEASE_CAS_RECEIPT",
    "ATOMIC_RELEASE_COUNTER_AND_OUTBOX_COMMIT",
    "FRESH_AUTHENTICATED_DISPATCH_CONTEXT",
    "EXACT_DELIVERY",
    "LOCAL_IMMUTABLE_ADMISSION",
    "DETERMINISTIC_SEMANTIC_EXTRACTION",
]


def _bridge_synthetic_type_refs() -> dict[str, str]:
    return {
        artifact_type.__name__: _BRIDGE_DATACLASS_TYPE_REFS[artifact_type]
        for artifact_type in sorted(
            _BRIDGE_DATACLASS_TYPES,
            key=lambda cls: cls.__name__,
        )
    }


def _bridge_route_class_profile() -> dict[str, dict[str, Any]]:
    _require(
        set(READ_ROUTE_CLASS_SHAPES) == set(_READ_ROUTE_CLASS_FAMILIES),
        "bridge route shape and route family sets differ",
    )
    return {
        route_class: {
            "channel_allowed": _READ_ROUTE_CLASS_FAMILIES[route_class][1],
            "family": _READ_ROUTE_CLASS_FAMILIES[route_class][0],
            "message_class": READ_ROUTE_CLASS_SHAPES[route_class][1],
            "plane": READ_ROUTE_CLASS_SHAPES[route_class][0],
        }
        for route_class in sorted(READ_ROUTE_CLASS_SHAPES)
    }


def _build_observer_read_capture_bridge_profile_base() -> dict[str, Any]:
    """Build the 16-key semantic profile without its commitment envelope."""

    profile = {
        "authority_chain": list(_OBSERVER_READ_CAPTURE_BRIDGE_AUTHORITY_CHAIN),
        "authorization": {
            "bounded_history_fixture_quota": {
                "capacity_claim": (
                    "MAXIMUM_ONE_ONLY_NO_N_CAPACITY_ALLOCATOR_OR_"
                    "CONCURRENCY_EXTRAPOLATION"
                ),
                "maximum_releases": 1,
                "scope": (
                    "EXACT_BOUNDED_SYNTHETIC_PROBE_FIXTURE_ONLY_NOT_A_"
                    "PROTOCOL_DEFAULT_OR_UNIVERSAL_LIMIT"
                ),
            },
            "capability_authority": "BOUNDED_CURRENT_READ_AUTHORITY_ONLY",
            "decision_authority_effect": ("PREFLIGHT_ONLY_RELEASE_RECHECK_REQUIRED"),
            "decision_seal_evidence": (
                "SYNTHETIC_HMAC_FIXTURE_ONLY_NOT_CRYPTOGRAPHIC_QUALIFICATION"
            ),
            "ingress_context_binds": [
                "OBSERVER_PRINCIPAL_AND_INSTANCE",
                "AUTHORIZATION_AUDIENCE",
                "PRODUCTION_SECURE_CONNECTION_INSTANCE",
                "REPLAY_DOMAIN",
                "DEFAULT_DENY_MANIFEST",
                "SECURITY_STATE_AND_EPOCH",
                "REVOCATION_EPOCH",
                "COORDINATOR_CLOCK_INCARNATION",
                "VERIFIED_AT_AND_EXCLUSIVE_NOT_AFTER",
            ],
            "ingress_provenance": ("SYNTHETIC_VERIFIED_AUTHORIZATION_SERVER_INGRESS"),
            "release_recheck": (
                "EXACT_CURRENT_PRINCIPAL_CONNECTION_SESSION_SECURITY_"
                "REVOCATION_MANIFEST_SCOPE_MEMBERSHIP_CURRENTNESS_AND_DEADLINE"
            ),
            "subscription_history_authority": False,
        },
        "canonical_type_system": {
            "embedded_suite_schema": ("ncp.b01.bridge-canonical-commitment-suite.v1"),
            "expanded_source_preflight": {
                "application_order": (
                    "BEFORE_SEMANTIC_COMPARISON_CANONICALIZATION_AND_DIGEST"
                ),
                "container_and_scalar_values_count_as_nodes": True,
                "mapping_keys_count_as_nodes": False,
                "maximum_collection_items_or_mapping_entries": (
                    MAX_BRIDGE_COLLECTION_ITEMS
                ),
                "maximum_depth_inclusive": MAX_BRIDGE_CANONICAL_DEPTH,
                "maximum_input_nodes_including_root": (MAX_BRIDGE_CANONICAL_NODES),
                "maximum_printable_ascii_octets_per_string_or_mapping_key": (
                    MAX_BRIDGE_STRING_OCTETS
                ),
                "maximum_standard_json_octets": (MAX_BRIDGE_CANONICAL_OCTETS),
                "root_depth": 0,
                "shared_or_cyclic_container": "REJECT",
            },
            "expanded_source_scalar_domain": (
                "PRINTABLE_ASCII_STRINGS_AND_PORTABLE_SAFE_INTEGERS_ONLY"
            ),
            "private_authoring_conversion": (
                "EXCLUSIVE_UNPUBLISHED_EXACT_DICT_LIST_TO_STRUCTURALLY_"
                "IMMUTABLE_GRAPH_WITH_SHARED_MUTABLE_AND_CYCLE_REJECTION_AND_"
                "REGISTERED_ARTIFACT_STABILITY_AS_A_CALLER_OBLIGATION"
            ),
            "registered_artifact_type_count": len(_BRIDGE_DATACLASS_TYPES),
            "registered_artifact_type_identity": (
                "EXACT_REGISTERED_FROZEN_DATACLASS_INSTANCE_NO_SUBCLASS"
            ),
            "runtime_emitter_input": (
                "EXACT_FROZEN_MAP_FROZEN_LIST_TUPLE_REGISTERED_ARTIFACT_OR_"
                "CLOSED_SCALAR_MUTABLE_DICT_LIST_REJECTED"
            ),
            "runtime_normalization_and_digest_framing": (
                "CANONICAL_COMMITMENT_SUITE_IS_COMPLETE_AUTHORITY"
            ),
            "same_process_integrity_boundary": {
                "artifact_instance_state": (
                    "CALLER_MUST_KEEP_STABLE_THROUGH_CALL_RETURN"
                ),
                "artifact_snapshot": (
                    "REVALIDATE_EACH_REACHED_CLASS_BEFORE_ITS_FIRST_INSTANCE_PER_"
                    "PUBLIC_TRAVERSAL_THEN_READ_EACH_INSTANCE_FIELD_ONCE_THROUGH_"
                    "OBJECT_GETATTRIBUTE"
                ),
                "error_construction": (
                    "EXACT_EXCEPTION_CLASS_WITH_NO_CALLER_DEFINED_NEW_OR_INIT"
                ),
                "field_metadata": (
                    "EXACT_SHARED_EMPTY_METADATA_SENTINEL_WITH_NO_CALLER_"
                    "MAPPING_DISPATCH"
                ),
                "frozen_mutator_guard": (
                    "STRUCTURAL_GENERATED_CODE_EQUIVALENCE_WITH_EXACT_CANDIDATE_"
                    "CLASS_AND_FROZEN_INSTANCE_ERROR_CLOSURE_AND_PINNED_FUNCTION_"
                    "CODE_GLOBALS_BUILTINS_STATE"
                ),
                "canonicalizer_and_interpreter_code_integrity": (
                    "CALLER_MUST_PRESERVE_THROUGH_CALL_RETURN"
                ),
                "concurrent_integrity_mutation": (
                    "CALLER_MUST_PREVENT_CLASS_INSTANCE_REGISTRY_OR_WRAPPER_"
                    "BACKING_MUTATION_THROUGH_CALL_RETURN"
                ),
                "non_slot_instance_state": (
                    "EXACT_NATIVE_DICT_WITH_KEYS_EXACTLY_EQUAL_TO_PINNED_FIELD_NAMES"
                ),
                "registration_pins": (
                    "DIRECT_OBJECT_FROZEN_DATACLASS_PARAMETERS_FIELDS_CLASS_"
                    "BINDINGS_AND_GENERATED_MUTATOR_STATE"
                ),
                "registry_snapshot": (
                    "EXACT_TUPLE_BACKING_GLOBAL_IDENTITY_ALIGNMENT_BOUNDS_AND_"
                    "DUPLICATE_REJECTION_BEFORE_TARGETED_ARTIFACT_READ"
                ),
                "registered_class_shape": (
                    "FROZEN_REGISTRY_PINNED_AT_REGISTRATION_EACH_REACHED_CLASS_"
                    "REVALIDATED_BEFORE_ITS_FIRST_INSTANCE_PER_PUBLIC_TRAVERSAL_"
                    "CALLER_MUST_PREVENT_CONCURRENT_MUTATION_THROUGH_CALL_RETURN"
                ),
                "scope": (
                    "SAME_PROCESS_INTEGRITY_EVIDENCE_ONLY_NOT_ATOMIC_SNAPSHOT_"
                    "OR_ADVERSARIAL_IN_PROCESS_SANDBOX"
                ),
                "structural_container_backing": (
                    "FROZEN_MAP_AND_FROZEN_LIST_BACKING_READ_ONCE_AND_CALLER_"
                    "STABLE_THROUGH_CALL_RETURN"
                ),
            },
            "unknown_unregistered_or_aliased_runtime_type": "REJECT",
        },
        "claim_boundary": (
            "SYNTHETIC_PRE_RATIFICATION_NON_NORMATIVE_B01_ARCHITECTURE_"
            "PROFILE_NOT_WIRE_RELEASE_LIVE_TRANSPORT_EXTERNAL_INDEPENDENT_"
            "INTEROPERABILITY_CONSUMER_QUALIFICATION_CRYPTOGRAPHIC_"
            "QUALIFICATION_OR_RELEASE_EVIDENCE"
        ),
        "commit": {
            "atomic_effects": [
                "CONSUME_EXACT_READ_DECISION",
                "INSTALL_RELEASE_COUNTER_SUCCESSOR",
                "ADVANCE_RELEASE_SEQUENCE_AND_OUTPUT_SLOT_ALLOCATORS",
                "INSTALL_IMMUTABLE_OUTBOX_ARTIFACT",
                "INSTALL_OUTBOX_STORAGE_STATE_HEAD",
                "INSTALL_OUTBOX_COMMIT_RECEIPT",
            ],
            "commit_provenance": (
                "SYNTHETIC_ATOMICALLY_COMMITTED_OBSERVER_READ_OUTBOX"
            ),
            "commit_receipt_provenance": (
                "SYNTHETIC_ATOMIC_OBSERVER_READ_OUTBOX_COMMIT"
            ),
            "exact_payload_binding": [
                "IMMUTABLE_PAYLOAD_BYTES",
                "SHA256_PAYLOAD_DIGEST",
                "PAYLOAD_OCTET_LENGTH",
            ],
            "installed_state_rule": (
                "ONE_TRANSACTION_AND_ONE_RECEIPT_INSTALL_THE_COUNTER_"
                "SUCCESSOR_AND_OUTBOX_WITHOUT_PARTIAL_VISIBILITY"
            ),
            "linearization_point": (
                "ATOMIC_OUTBOX_COMMIT_IS_THE_ONLY_RELEASE_QUOTA_SLOT_AND_"
                "PAYLOAD_VISIBILITY_LINEARIZATION"
            ),
            "transaction_identity": (
                "FULL_RELEASE_CAS_COMMITTED_OUTBOX_ARTIFACT_AND_INSTALLED_"
                "STORAGE_HEAD_NOT_THE_QUOTA_SUCCESSOR_ALONE"
            ),
            "reservation_fence": {
                "authority_effect": "NONAUTHORIZING_EXCLUSIVE_RECOVERABLE_FENCE",
                "before_outbox_commit": [
                    "DO_NOT_CONSUME_READ_DECISION_OR_RELEASE_QUOTA",
                    "DO_NOT_INSTALL_RELEASE_COUNTER_SUCCESSOR",
                    "DO_NOT_ADVANCE_RELEASE_SEQUENCE_OR_OUTPUT_SLOT_ALLOCATORS",
                    "DO_NOT_INSTALL_USED_RELEASE_IDENTITY_OR_OUTPUT_SLOT",
                    "DO_NOT_EXPOSE_OUTBOX_PAYLOAD_OR_SUCCESS_RECEIPT",
                ],
                "crash_recovery": (
                    "PRESERVE_ONLY_THE_EXACT_PENDING_FENCE_WITH_ZERO_"
                    "RELEASE_QUOTA_OR_ALLOCATOR_EFFECT"
                ),
                "exact_retry": "RETURN_THE_SAME_PENDING_FENCE_OR_COMMITTED_RESULT",
                "slot_semantics": (
                    "INTENDED_SEQUENCE_AND_SLOT_ARE_ADVISORY_ONLY_AND_MAY_"
                    "MATCH_AN_UNRELATED_PENDING_INTENT"
                ),
                "terminal_rule": (
                    "CANCEL_TO_A_PERMANENT_TOMBSTONE_WITHOUT_RELEASE_"
                    "CONSUMPTION_COUNTER_SUCCESSOR_OR_OUTBOX"
                ),
            },
            "winning_commit_revalidation": [
                "RELOAD_EXACT_POST_RESERVATION_OUTER_MAP_AND_ENTRY_HEADS",
                "DERIVE_FRESH_ACTUAL_RELEASE_SEQUENCE_AND_OUTPUT_SLOT",
                "REISSUE_CURRENTNESS_EVIDENCE_AND_EXACT_STATE_CUT",
                "REBUILD_RELEASE_CAS_AND_VALIDATED_RECEIPT",
                "COINSTALL_DECISION_CONSUMPTION_COUNTER_SUCCESSOR_ALLOCATOR_"
                "ADVANCES_ENTRY_AND_OUTER_SUCCESSORS_RECEIPT_AND_OUTBOX",
            ],
            "preconditions": [
                "VALIDATED_RELEASE_CAS_RECEIPT",
                "EXPECTED_PRIOR_OUTBOX_STORAGE_STATE_HEAD",
                "COMMIT_AT_BEFORE_EFFECTIVE_EXCLUSIVE_DEADLINE",
            ],
            "stable_identity_binding": [
                "STABLE_OUTBOX_ITEM_ID",
                "RELEASE_IDEMPOTENCY_KEY",
                "TRANSPORT_IDEMPOTENCY_KEY",
                "RECIPIENT_PRINCIPAL_AND_INSTANCE",
                "CANONICAL_SCOPE_AND_BOUNDARY_MEMBERSHIP",
                "RELEASE_ORDINAL",
            ],
        },
        "currentness": {
            "current_evidence_required": True,
            "evidence_provenance": (
                "SYNTHETIC_AUTHENTICATED_BOUNDARY_GRANT_CURRENTNESS"
            ),
            "release_counter_prestate": (
                "EXACT_BOUNDARY_GRANT_ENTRY_VERSION_AND_PRIOR_RELEASE_COUNT"
            ),
            "state_cut_binds": [
                "BOUNDARY_STATE_HEAD",
                "GRANT_ENTRY_HEAD",
                "STATE_VERSION",
                "PRIOR_RELEASE_COUNT",
                "GRANT_CURRENTNESS_RECEIPT",
                "LOCAL_GRANT_EXCLUSIVE_NOT_AFTER",
                "CURRENTNESS_EVIDENCE_ARTIFACT",
                "SECURITY_STATE_AND_EPOCH",
                "REVOCATION_EPOCH",
            ],
            "successor_selection": (
                "DOMAIN_SEPARATED_FROM_PRIOR_COUNTER_STATE_RELEASE_"
                "IDEMPOTENCY_KEY_AND_RELEASE_ORDINAL"
            ),
            "successor_scope": (
                "QUOTA_STATE_ONLY_NOT_A_TRANSACTION_OUTBOX_OR_STORAGE_IDENTITY"
            ),
            "time_relation": (
                "VERIFIED_AT_LE_CHECKED_AT_LT_EVIDENCE_EXCLUSIVE_NOT_AFTER_"
                "LE_LOCAL_GRANT_EXCLUSIVE_NOT_AFTER"
            ),
        },
        "deadline_and_clock": {
            "clock_identity": (
                "EXACT_CANONICAL_UUID4_CLOCK_INCARNATIONS_NO_DIRECT_"
                "CROSS_CLOCK_COMPARISON"
            ),
            "effective_release_deadline": {
                "operation": "MINIMUM",
                "operands": [
                    "LOCAL_GRANT_EXCLUSIVE_NOT_AFTER",
                    "GRANT_CURRENTNESS_EXCLUSIVE_NOT_AFTER",
                    "CONSERVATIVELY_MAPPED_DECISION_EXCLUSIVE_NOT_AFTER",
                    "LOCAL_RELEASE_CONTEXT_EXCLUSIVE_NOT_AFTER",
                ],
                "semantics": "EXCLUSIVE_NOT_AFTER",
            },
            "mapping_applicability": (
                "SOURCE_AND_TARGET_REFERENCES_AND_MAPPED_DEADLINE_MUST_"
                "REMAIN_INSIDE_THEIR_QUALIFIED_APPLICABILITY_INTERVALS"
            ),
            "mapping_provenance": (
                "SYNTHETIC_AUTHENTICATED_CONSERVATIVE_CLOCK_MAPPING"
            ),
            "mapping_state_cut": (
                "INDEPENDENT_EXACT_AUTHORITY_QUALIFICATION_SOURCE_RECEIPT_"
                "POLICY_CLOCK_REFERENCE_RATE_ROUNDING_APPLICABILITY_"
                "SECURITY_AND_MAPPED_DEADLINE_CUT"
            ),
            "mapping_rule": (
                "BOUNDARY_REFERENCE_LOWER_PLUS_FLOOR_SOURCE_DELTA_TIMES_"
                "MINIMUM_RATE_NUMERATOR_OVER_DENOMINATOR"
            ),
            "rounding_rule": "LOWER_FLOOR",
            "source_receipt_current_required": True,
        },
        "delivery_admission": {
            "admission_is_immutable_historical_evidence": True,
            "capsule_future_read_authority": False,
            "delivery_binds": [
                "VERIFIED_TRANSPORT_PRINCIPAL",
                "LIVE_CONNECTION",
                "REPLAY_DOMAIN",
                "SESSION_GENERATION",
                "SECURITY_STATE_AND_EPOCH",
                "REVOCATION_EPOCH",
                "DEFAULT_DENY_MANIFEST",
                "CANONICAL_READ_SCOPE",
                "BOUNDARY_SCOPE_MEMBERSHIP",
                "READ_DECISION",
                "RELEASE_RECIPIENT_CONTEXT",
                "QUALIFIED_DEADLINE_MAPPING",
                "GRANT_CURRENTNESS_STATE_CUT",
                "VALIDATED_RELEASE_CAS_RECEIPT",
                "COMMITTED_OUTBOX_ARTIFACT",
                "OUTBOX_COMMIT_RECEIPT",
                "EXPECTED_DISPATCH_DESTINATION_CUT",
                "ENDPOINT_CONNECTION_AND_REPLAY_DOMAIN",
                "TRANSPORT_GATE_STATE_DIGEST_AND_EPOCH",
                "FRESH_AUTHENTICATED_DISPATCH_CONTEXT",
                "EXACT_PAYLOAD_BYTES_DIGEST_AND_LENGTH",
            ],
            "security_cut_rule": (
                "ADMITTED_BEFORE_CUT_REMAINS_HISTORICAL_WITHOUT_FUTURE_READ_AUTHORITY"
            ),
        },
        "dispatch": {
            "artifact_rule": (
                "DISPATCH_ONLY_THE_EXACT_ATOMICALLY_COMMITTED_OUTBOX_"
                "ARTIFACT_AND_ITS_VALIDATED_RECEIPTS"
            ),
            "definitive_outcome_rule": (
                "DELIVERED_OR_REJECTED_IS_TERMINAL_AND_FORBIDS_RESEND"
            ),
            "exactly_once_claim": False,
            "context_binds": [
                "BOUNDARY_AND_RECIPIENT_PRINCIPAL_AND_INSTANCE",
                "STABLE_OUTBOX_ITEM_ID",
                "EXACT_PAYLOAD_DIGEST_AND_LENGTH",
                "VALIDATED_RELEASE_CAS_RECEIPT",
                "OUTBOX_COMMIT_RECEIPT_AND_INSTALLED_STORAGE_HEAD",
                "RELEASE_COUNTER_SUCCESSOR",
                "EXPECTED_DISPATCH_DESTINATION_CUT",
                "CANONICAL_SCOPE_AND_BOUNDARY_MEMBERSHIP",
                "ENDPOINT_PROFILE_CONNECTION_INSTANCE_AND_REPLAY_DOMAIN",
                "TRANSPORT_GATE_STATE_DIGEST_AND_EPOCH",
                "TRANSPORT_IDEMPOTENCY_KEY",
                "BOUNDARY_CLOCK_INCARNATION",
                "LOCAL_SECURITY_STATE_AND_EPOCH",
                "LOCAL_REVOCATION_EPOCH",
            ],
            "endpoint_profile": "production-secure",
            "freshness": (
                "COMMIT_AT_LT_DISPATCH_VERIFIED_AT_LE_CHECKED_AT_LT_"
                "DISPATCH_EXCLUSIVE_NOT_AFTER_LE_EFFECTIVE_RELEASE_"
                "EXCLUSIVE_NOT_AFTER"
            ),
            "post_commit_context": (
                "INDEPENDENT_EXACT_LIVE_DESTINATION_CONNECTION_REPLAY_"
                "SECURITY_REVOCATION_TRANSPORT_GATE_AND_DEADLINE_CUT"
            ),
            "post_commit_revocation_rule": (
                "GRANT_TERMINALIZATION_OR_REVOCATION_ORDERED_AFTER_ATOMIC_"
                "OUTBOX_COMMIT_DOES_NOT_RETRACT_THE_COMMITTED_IMMUTABLE_"
                "ITEM;_DISPATCH_DOES_NOT_REAUTHORIZE_GRANT_OR_MANIFEST_AND_"
                "CANNOT_MINT_OR_WIDEN_RELEASE"
            ),
            "provenance": ("SYNTHETIC_FRESH_AUTHENTICATED_OUTBOX_DISPATCH"),
            "remote_result_local_ack_crash": (
                "AMBIGUOUS_UNKNOWN_NO_DELIVERY_SUCCESS_OR_REJECTION_INFERRED"
            ),
            "retry_after_ambiguous_requires": [
                "SAME_COMMITTED_PAYLOAD_BYTES_DIGEST_AND_LENGTH",
                "SAME_STABLE_OUTBOX_ITEM_AND_RELEASE_IDENTITY",
                "SAME_TRANSPORT_IDEMPOTENCY_KEY",
                "SAME_STABLE_PHYSICAL_DESTINATION_IDENTITY",
                "FRESH_EXACT_TRANSPORT_GATE_CUT_PER_ATTEMPT",
                "FRESH_UNIQUE_ATTEMPT_IDENTITY_AND_NEXT_SEQUENCE",
                "AUTHENTICATED_RECEIVER_DEDUPLICATION_PROOF_BOUND_TO_THE_"
                "PRIOR_AMBIGUOUS_DISPOSITION",
            ],
            "retry_proof_boundary": (
                "SYNTHETIC_FIXTURE_ONLY_NOT_LIVE_TRANSPORT_OR_RECEIVER_"
                "EXACTLY_ONCE_QUALIFICATION"
            ),
        },
        "exact_type_refs": {
            "admission_capsule": (
                "delivered-admission-evidence-capsule-type::"
                "DeliveredAdmissionEvidenceCapsule"
            ),
            "boundary_membership": (
                "observer-boundary-read-scope-membership-type::"
                "ObserverBoundaryReadScopeMembership"
            ),
            "canonical_scope": (
                "canonical-observer-read-scope-type::CanonicalObserverReadScope"
            ),
            "extraction_contract": (
                "deterministic-extraction-contract-type::"
                "DeterministicExtractionContract"
            ),
            "extraction_receipt": (
                "deterministic-extraction-receipt-type::DeterministicExtractionReceipt"
            ),
            "sealed_decision": (
                "sealed-observer-read-authorization-decision-type::"
                "SealedObserverReadAuthorizationDecision"
            ),
        },
        "release_cas": {
            "candidate_authority_effect": (
                "VALIDATION_CANDIDATE_ONLY_NO_INSTALLED_STATE"
            ),
            "candidate_binds": [
                "OBSERVER_PRINCIPAL_AND_INSTANCE",
                "SOURCE_SESSION_KIND_ID_AND_GENERATION",
                "CANONICAL_SCOPE_AND_BOUNDARY_MEMBERSHIP",
                "CALLER_OPERATION_AND_REQUEST",
                "RELEASE_IDEMPOTENCY_KEY",
                "AUTHORIZATION_INGRESS_CONTEXT",
                "RELEASE_RECIPIENT_CONTEXT",
                "READ_DECISION",
                "GRANT_CURRENTNESS_EVIDENCE",
                "QUALIFIED_DEADLINE_MAPPING",
                "PRIOR_AND_SUCCESSOR_RELEASE_COUNTER_HEADS",
                "EFFECTIVE_RELEASE_DEADLINE",
            ],
            "ordinal_rule": (
                "RELEASE_ORDINAL_EQUALS_PRIOR_RELEASE_COUNT_PLUS_ONE_AND_"
                "MUST_NOT_EXCEED_DECISION_MAXIMUM_RELEASE_COUNT"
            ),
            "receipt_binds": [
                "EXACT_RELEASE_CAS",
                "VALIDATOR_PRINCIPAL_AND_INSTANCE",
                "BOUNDARY_CLOCK_INCARNATION",
                "AUTHORIZATION_STATE_CUT",
                "GRANT_CURRENTNESS_STATE_CUT",
                "QUALIFIED_DEADLINE_MAPPING_STATE_CUT",
                "CHECKED_AT_AND_EFFECTIVE_RELEASE_DEADLINE",
            ],
            "receipt_provenance": (
                "SYNTHETIC_FULL_OBSERVER_READ_RELEASE_CAS_VALIDATION"
            ),
            "state_installation": (
                "ONLY_THE_ATOMIC_RELEASE_COUNTER_AND_OUTBOX_COMMIT_"
                "INSTALLS_THE_SUCCESSOR"
            ),
        },
        "route_classes": {
            "additional_closed_disposition": ["OBSERVATION_COMMAND_DISPOSITION"],
            "closed_shapes": _bridge_route_class_profile(),
            "current_prisoma_delivery": [
                "ACTION_COMMAND_PROPOSAL",
                "OBSERVATION_FRAME",
                "PERCEPTION_PROJECTED_OBSERVATION",
                "PERCEPTION_SENSOR_FRAME",
            ],
            "history_domain_rule": (
                "CONTENT_ADDRESSED_HISTORY_DOMAIN_SEPARATE_FROM_LIVE_ROUTE"
            ),
            "live_route_rule": (
                "EXACT_REALM_SESSION_FAMILY_AND_OPTIONAL_ADMITTED_CHANNEL"
            ),
            "operations": list(READ_OPERATIONS),
            "unknown_route_class_operation_family_or_channel": "REJECT",
        },
        "schema": "ncp.b01-observer-read-capture-bridge-profile.v2",
        "semantic_extraction": {
            "axis_members": {
                "A": ["a0"],
                "D": ["d_left", "d_right"],
                "L": ["l0"],
                "V": ["v0"],
            },
            "deterministic_receipt_count": 7,
            "fixture_scope": (
                "EXACT_SYNTHETIC_NON_VACUITY_MATRIX_ONLY_NOT_A_PROTOCOL_CARDINALITY"
            ),
            "replay": "REQUIRED_FOR_EACH_SEMANTIC_MEMBER_SAMPLE",
            "source": "RETAINED_ADMITTED_PAYLOAD_BYTES",
        },
        "synthetic_bridge_type_refs": _bridge_synthetic_type_refs(),
        "unknown_default_missing_duplicate_or_substituted": "REJECT",
    }
    _require(
        type(profile) is dict
        and len(profile) == 16
        and frozenset(profile) == _OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_BASE_KEYS,
        "bridge base profile key set is not the exact 16-key contract",
    )
    return profile


def _build_observer_read_capture_bridge_profile() -> dict[str, Any]:
    profile = _build_observer_read_capture_bridge_profile_base()
    profile["canonical_commitment"] = {
        "suite": bridge_commitment_suite(),
        "suite_digest": bridge_commitment_suite_digest(),
        "suite_digest_domain": bridge_commitment_suite_digest_domain(),
    }
    _require(
        len(profile) == 17
        and frozenset(profile) == _OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_KEYS,
        "bridge full profile key set is not the exact 17-key contract",
    )
    return profile


_OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_VALUE = (
    _build_observer_read_capture_bridge_profile()
)
_validate_printable_ascii_safe_json(
    _OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_VALUE,
    label="observer read capture bridge profile",
)
_OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_JSON = json.dumps(
    _OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_VALUE,
    allow_nan=False,
    ensure_ascii=False,
    separators=(",", ":"),
    sort_keys=True,
).encode("utf-8")
del _OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_VALUE
_OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_COMPUTED_DIGEST = _owned_json_domain_digest(
    _OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_DOMAIN,
    json.loads(_OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_JSON),
)
_OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_EXPECTED_DIGEST = (
    "4226b60f52d799e36be6446d1069ed0d79efe910895f1ba6301ba949a49ded0a"
)
_require(
    hmac.compare_digest(
        _OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_COMPUTED_DIGEST,
        _OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_EXPECTED_DIGEST,
    ),
    "observer read capture bridge profile differs from its frozen digest",
)


def observer_read_capture_bridge_profile_digest_domain() -> str:
    """Return the external digest domain for the complete v2 profile."""

    return _OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_DOMAIN


def observer_read_capture_bridge_profile_digest() -> str:
    """Return the frozen domain-separated digest of the complete v2 profile."""

    return _OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_EXPECTED_DIGEST


def validate_observer_read_capture_bridge_profile(profile: Any) -> None:
    """Require the exact closed 17-key profile and embedded commitment suite."""

    _require(type(profile) is dict, "bridge profile root type is not exact")
    _require(
        len(profile) == 17
        and frozenset(profile) == _OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_KEYS,
        "bridge profile key set is not the exact 17-key contract",
    )
    _validate_printable_ascii_safe_json(
        profile,
        label="supplied observer read capture bridge profile",
    )
    commitment = profile["canonical_commitment"]
    _require(
        type(commitment) is dict
        and frozenset(commitment)
        == frozenset({"suite", "suite_digest", "suite_digest_domain"}),
        "bridge profile canonical commitment is not the exact closed triple",
    )
    validate_bridge_commitment_suite(
        commitment["suite"],
        expected_suite_digest_domain=commitment["suite_digest_domain"],
        expected_suite_digest=commitment["suite_digest"],
    )
    expected_type_refs = _bridge_synthetic_type_refs()
    _require(
        profile["synthetic_bridge_type_refs"] == expected_type_refs
        and profile["canonical_type_system"]["registered_artifact_type_count"]
        == len(expected_type_refs),
        "bridge profile synthetic type references are incomplete or aliased",
    )
    expected_registry = [
        {
            "field_order": list(field_names),
            "type_ref": stable_id,
        }
        for stable_id, field_names in sorted(
            _BRIDGE_DATACLASS_TYPE_REFS.revalidated_shape_view(),
            key=lambda item: item[0],
        )
    ]
    _require(
        commitment["suite"]["type_registry"] == expected_registry,
        "bridge profile commitment suite type registry differs from runtime",
    )
    _require(
        profile["route_classes"]["closed_shapes"] == _bridge_route_class_profile(),
        "bridge profile route shapes differ from runtime",
    )
    standard_json = json.dumps(
        profile,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    _require(
        hmac.compare_digest(
            standard_json,
            _OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_JSON,
        )
        and bool(_OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_COMPUTED_DIGEST),
        "bridge profile content or frozen digest differs",
    )


def observer_read_capture_bridge_profile() -> dict[str, Any]:
    """Return an isolated, validated copy of the exact bridge profile."""

    profile = json.loads(_OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_JSON)
    validate_observer_read_capture_bridge_profile(profile)
    return profile


def observer_read_capture_bridge_profile_mutation_report() -> dict[str, Any]:
    """Mutate the complete base profile and the commitment triple."""

    profile = observer_read_capture_bridge_profile()
    base = {
        key: profile[key]
        for key in sorted(_OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_BASE_KEYS)
    }
    base_leaf_rejections = 0
    for path in _suite_leaf_paths(base):
        mutant = observer_read_capture_bridge_profile()
        parent, component = _suite_path_parent(mutant, path)
        parent[component] = _mutated_suite_leaf(parent[component])
        try:
            validate_observer_read_capture_bridge_profile(mutant)
        except BridgeValidationError:
            base_leaf_rejections += 1
        else:
            raise BridgeValidationError(
                "bridge profile accepted one base-profile leaf mutation"
            )

    base_sequence_order_rejections = 0
    for path in _suite_list_paths(base):
        mutant = observer_read_capture_bridge_profile()
        parent, component = _suite_path_parent(mutant, path)
        sequence = parent[component]
        swap_index = next(
            (
                index
                for index in range(1, len(sequence))
                if sequence[index] != sequence[0]
            ),
            None,
        )
        if swap_index is None:
            continue
        sequence[0], sequence[swap_index] = (
            sequence[swap_index],
            sequence[0],
        )
        try:
            validate_observer_read_capture_bridge_profile(mutant)
        except BridgeValidationError:
            base_sequence_order_rejections += 1
        else:
            raise BridgeValidationError(
                "bridge profile accepted one base-profile sequence reorder"
            )

    top_level_removal_rejections = 0
    for key in sorted(profile):
        mutant = observer_read_capture_bridge_profile()
        del mutant[key]
        try:
            validate_observer_read_capture_bridge_profile(mutant)
        except BridgeValidationError:
            top_level_removal_rejections += 1
        else:
            raise BridgeValidationError(
                "bridge profile accepted one missing top-level member"
            )

    unknown_member_mutant = observer_read_capture_bridge_profile()
    unknown_member_mutant["unknown_extension"] = "MUST_REJECT"
    try:
        validate_observer_read_capture_bridge_profile(unknown_member_mutant)
    except BridgeValidationError:
        unknown_member_rejections = 1
    else:
        raise BridgeValidationError("bridge profile accepted an unknown member")

    commitment_mutations: tuple[tuple[str, Any], ...] = (
        (
            "suite_digest_domain_substitution",
            "ncp.b01.bridge.CanonicalCommitmentSuiteMutant@1",
        ),
        ("suite_digest_substitution", "f" * 64),
        ("suite_substitution", None),
    )
    commitment_rejected: list[str] = []
    for name, replacement in commitment_mutations:
        mutant = observer_read_capture_bridge_profile()
        commitment = mutant["canonical_commitment"]
        if name == "suite_substitution":
            commitment["suite"]["claim_boundary"] += "_MUTATED"
            commitment["suite_digest"] = _owned_json_domain_digest(
                commitment["suite_digest_domain"],
                commitment["suite"],
            )
        elif name == "suite_digest_domain_substitution":
            commitment["suite_digest_domain"] = replacement
        else:
            commitment["suite_digest"] = replacement
        try:
            validate_observer_read_capture_bridge_profile(mutant)
        except BridgeValidationError:
            commitment_rejected.append(name)
        else:
            raise BridgeValidationError(
                f"bridge profile accepted {name.replace('_', ' ')}"
            )
    _require(
        len(commitment_rejected) == len(commitment_mutations),
        "bridge profile commitment mutation and rejection counts differ",
    )
    total_mutations = (
        len(_suite_leaf_paths(base))
        + base_sequence_order_rejections
        + len(profile)
        + unknown_member_rejections
        + len(commitment_mutations)
    )
    total_rejections = (
        base_leaf_rejections
        + base_sequence_order_rejections
        + top_level_removal_rejections
        + unknown_member_rejections
        + len(commitment_rejected)
    )
    _require(
        total_mutations == total_rejections,
        "bridge profile mutation and rejection counts differ",
    )
    return {
        "base_leaf_mutations_rejected": base_leaf_rejections,
        "base_sequence_order_mutations_rejected": (base_sequence_order_rejections),
        "commitment_mutation_names": commitment_rejected,
        "commitment_triple_mutations_rejected": len(commitment_rejected),
        "top_level_removal_mutations_rejected": top_level_removal_rejections,
        "total_mutations_executed": total_mutations,
        "total_mutations_rejected": total_rejections,
        "unknown_member_mutations_rejected": unknown_member_rejections,
    }


def validate_bridge_canonical_type_system() -> None:
    """Reject canonical type erasure in the shared bridge encoder."""

    from collections.abc import Mapping as AbstractMapping
    from types import MappingProxyType

    class LyingTypeRegistry(AbstractMapping[type[Any], str]):
        def __init__(self) -> None:
            self.iterations = 0

        def __len__(self) -> int:
            return 1

        def __iter__(self):
            self.iterations += 1
            return iter((int,) * 100_000)

        def __getitem__(self, key: type[Any]) -> str:
            if key is int:
                return "ncp.b01.bridge.Hostile@1"
            raise KeyError(key)

    lying_registry = LyingTypeRegistry()
    try:
        _bounded_canonical_bytes(
            None,
            style="bridge",
            limits=_BRIDGE_CANONICAL_LIMITS,
            type_ids=MappingProxyType(lying_registry),
            error_type=BridgeValidationError,
        )
    except BridgeValidationError:
        pass
    else:
        raise BridgeValidationError("generic mappingproxy registry was accepted")
    _require(
        lying_registry.iterations == 0,
        "rejected generic mappingproxy registry was iterated before rejection",
    )

    suite = bridge_commitment_suite()
    _validate_printable_ascii_safe_json(
        suite,
        label="bridge expanded-source suite",
    )
    for hostile_scalar in ("β", "\n", "\x00", "\ud800"):
        try:
            _validate_printable_ascii_safe_json(
                {"hostile_scalar": hostile_scalar},
                label="hostile bridge expanded-source suite",
            )
        except BridgeValidationError:
            continue
        raise BridgeValidationError(
            "bridge expanded-source suite accepted a non-ASCII or control scalar"
        )

    maximum_depth_json: Any = None
    for _index in range(MAX_BRIDGE_CANONICAL_DEPTH):
        maximum_depth_json = [maximum_depth_json]
    _validate_printable_ascii_safe_json(
        maximum_depth_json,
        label="maximum-depth expanded-source vector",
    )
    first_over_depth_json = [maximum_depth_json]

    maximum_node_json = [
        [None] * 4_095,
        [None] * 4_095,
        [None] * 4_095,
        [None] * 4_094,
    ]
    _require(
        1 + len(maximum_node_json) + sum(map(len, maximum_node_json))
        == MAX_BRIDGE_CANONICAL_NODES,
        "maximum-node expanded-source vector count changed",
    )
    _validate_printable_ascii_safe_json(
        maximum_node_json,
        label="maximum-node expanded-source vector",
    )
    first_over_node_json = [
        *maximum_node_json[:3],
        [None] * 4_095,
    ]

    maximum_collection_json = [None] * MAX_BRIDGE_COLLECTION_ITEMS
    _validate_printable_ascii_safe_json(
        maximum_collection_json,
        label="maximum-collection expanded-source vector",
    )
    first_over_collection_json = [None] * (MAX_BRIDGE_COLLECTION_ITEMS + 1)

    maximum_string_json = "x" * MAX_BRIDGE_STRING_OCTETS
    _validate_printable_ascii_safe_json(
        maximum_string_json,
        label="maximum-string expanded-source vector",
    )
    maximum_key_json = {maximum_string_json: None}
    _validate_printable_ascii_safe_json(
        maximum_key_json,
        label="maximum-key expanded-source vector",
    )

    canonical_limit_string_lengths = [
        1_048_573,
        1_048_573,
        1_048_573,
        1_048_573,
        1_048_573,
        1_048_573,
        1_048_573,
        1_048_572,
    ]
    maximum_canonical_json = ["x" * length for length in canonical_limit_string_lengths]
    _require(
        len(
            json.dumps(
                maximum_canonical_json,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        == MAX_BRIDGE_CANONICAL_OCTETS,
        "maximum-canonical-octet expanded-source vector changed",
    )
    _validate_printable_ascii_safe_json(
        maximum_canonical_json,
        label="maximum-canonical-octet expanded-source vector",
    )
    first_over_canonical_json = [
        *maximum_canonical_json[:-1],
        maximum_canonical_json[-1] + "x",
    ]

    expanded_source_first_over_vectors: tuple[Any, ...] = (
        first_over_depth_json,
        first_over_node_json,
        first_over_collection_json,
        maximum_string_json + "x",
        {maximum_string_json + "x": None},
        first_over_canonical_json,
    )
    for first_over_vector in expanded_source_first_over_vectors:
        try:
            _validate_printable_ascii_safe_json(
                first_over_vector,
                label="first-over expanded-source preflight vector",
            )
        except BridgeValidationError:
            continue
        raise BridgeValidationError(
            "expanded-source preflight accepted one first-over-limit vector"
        )

    def reject_immutable_limit(value: Any, *, label: str) -> None:
        try:
            _canonical_bytes(value)
        except BridgeValidationError:
            return
        raise BridgeValidationError(f"{label} first-over immutable vector was accepted")

    exact_depth: Any = None
    for _index in range(MAX_BRIDGE_CANONICAL_DEPTH):
        exact_depth = FrozenList((exact_depth,))
    _canonical_bytes(exact_depth)
    reject_immutable_limit(
        FrozenList((exact_depth,)),
        label="depth",
    )

    exact_nodes = FrozenList(
        (
            FrozenList((None,) * 4_095),
            FrozenList((None,) * 4_095),
            FrozenList((None,) * 4_095),
            FrozenList((None,) * 4_094),
        )
    )
    _canonical_bytes(exact_nodes)
    reject_immutable_limit(
        FrozenList(
            (
                FrozenList((None,) * 4_095),
                FrozenList((None,) * 4_095),
                FrozenList((None,) * 4_095),
                FrozenList((None,) * 4_095),
            )
        ),
        label="node",
    )

    _canonical_bytes(FrozenList((None,) * MAX_BRIDGE_COLLECTION_ITEMS))
    reject_immutable_limit(
        FrozenList((None,) * (MAX_BRIDGE_COLLECTION_ITEMS + 1)),
        label="collection",
    )
    _canonical_bytes("x" * MAX_BRIDGE_STRING_OCTETS)
    reject_immutable_limit(
        "x" * (MAX_BRIDGE_STRING_OCTETS + 1),
        label="string",
    )
    _canonical_bytes(b"x" * MAX_BRIDGE_PAYLOAD_OCTETS)
    reject_immutable_limit(
        b"x" * (MAX_BRIDGE_PAYLOAD_OCTETS + 1),
        label="payload",
    )
    exact_output = FrozenList(
        (
            *(("x" * MAX_BRIDGE_STRING_OCTETS) for _index in range(7)),
            "x" * 1_048_519,
        )
    )
    _require(
        len(_canonical_bytes(exact_output)) == MAX_BRIDGE_CANONICAL_OCTETS,
        "exact canonical output boundary vector changed",
    )
    reject_immutable_limit(
        FrozenList((*exact_output.items[:-1], exact_output.items[-1] + "x")),
        label="canonical output",
    )

    revalidated_shapes = _BRIDGE_DATACLASS_TYPE_REFS.revalidated_shape_view()
    _require(
        len(set(_BRIDGE_DATACLASS_TYPE_REFS.values())) == len(_BRIDGE_DATACLASS_TYPES)
        and len(revalidated_shapes) == len(_BRIDGE_DATACLASS_TYPES)
        and all(
            type(type_ref) is str
            and type_ref == f"ncp.b01.bridge.{artifact_type.__name__}@1"
            and shape_type_ref is type_ref
            and len(field_names) <= MAX_BRIDGE_ARTIFACT_FIELDS
            for (artifact_type, type_ref), (shape_type_ref, field_names) in zip(
                _BRIDGE_DATACLASS_TYPE_REFS.items(),
                revalidated_shapes,
                strict=True,
            )
        ),
        "bridge artifact type references are missing, aliased, or unstable",
    )
    collision_challenges: tuple[Any, ...] = (
        b"x",
        FrozenMap((("$bridge_kind", "immutable_bytes"), ("hex", "78"))),
        ("x",),
        FrozenList(("x",)),
        FrozenMap((("0", "x"),)),
    )
    encodings = tuple(_canonical_bytes(value) for value in collision_challenges)
    _require(
        len(set(encodings)) == len(encodings)
        and all(encoded.isascii() for encoded in encodings),
        "bridge bytes, mapping, tuple, or list canonical domains collide",
    )
    reference_inputs = _bridge_reference_inputs()
    _require(
        set(reference_inputs) == set(_BRIDGE_REFERENCE_OUTPUT_HEX)
        and all(
            _canonical_bytes(reference_inputs[name]).hex()
            == _BRIDGE_REFERENCE_OUTPUT_HEX[name]
            for name in reference_inputs
        ),
        "bridge canonical reference vector output changed",
    )
    reverse_unicode_order_authoring = {
        "\U00010000": "ASTRAL_PLANE_ONE",
        "\ue000": "BMP_PRIVATE_USE",
    }
    frozen_unicode_order = _freeze_owned_bridge_json(reverse_unicode_order_authoring)
    _require(
        type(frozen_unicode_order) is FrozenMap
        and tuple(key for key, _value in frozen_unicode_order.entries)
        == ("\ue000", "\U00010000")
        and _canonical_bytes(frozen_unicode_order).hex()
        == _BRIDGE_REFERENCE_OUTPUT_HEX["unicode_scalar_order"],
        "bridge authoring conversion does not use Unicode scalar key order",
    )
    reference_frame = _domain_frame(
        _BRIDGE_REFERENCE_DOMAIN,
        FrozenMap((("a", 1),)),
    )
    _require(
        reference_frame.hex() == _BRIDGE_REFERENCE_FRAME_HEX
        and hashlib.sha256(reference_frame).hexdigest()
        == _BRIDGE_REFERENCE_FRAME_DIGEST,
        "bridge digest-frame reference vector changed",
    )
    validate_bridge_commitment_suite(
        suite,
        expected_suite_digest_domain=bridge_commitment_suite_digest_domain(),
        expected_suite_digest=bridge_commitment_suite_digest(),
    )

    class StringAlias(str):
        pass

    class IntegerAlias(int):
        pass

    class BytesAlias(bytes):
        pass

    class ListAlias(list[Any]):
        pass

    class TupleAlias(tuple[Any, ...]):
        pass

    class DictAlias(dict[str, Any]):
        pass

    @dataclass(frozen=True)
    class UnregisteredArtifact:
        value: int

    invalid_domains: tuple[Any, ...] = (
        StringAlias(_BRIDGE_REFERENCE_DOMAIN),
        "ncp.b01.bridge.@1",
        "ncp.b01.bridge.ReferenceVector@2",
        "ncp.b01.bridge.Reference/Vector@1",
        "ncp.b01.bridge.Référence@1",
        "ncp.b01.bridge.Reference\x00Vector@1",
        "ncp.b01.bridge." + ("a" * MAX_BRIDGE_DOMAIN_OCTETS) + "@1",
    )
    for invalid_domain in invalid_domains:
        try:
            _domain_frame(invalid_domain, None)
        except BridgeValidationError:
            continue
        raise BridgeValidationError("invalid bridge digest domain was accepted")

    cycle: list[Any] = []
    cycle.append(cycle)
    too_deep: Any = None
    for _index in range(MAX_BRIDGE_CANONICAL_DEPTH + 1):
        too_deep = [too_deep]
    excessive_nodes = [
        [None, None, None] for _index in range(MAX_BRIDGE_COLLECTION_ITEMS)
    ]
    maximum_string = "x" * MAX_BRIDGE_STRING_OCTETS
    invalid_values: tuple[Any, ...] = (
        0.0,
        bytearray(b"x"),
        memoryview(b"x"),
        IntegerAlias(1),
        BytesAlias(b"x"),
        ListAlias([None]),
        TupleAlias((None,)),
        DictAlias({"a": None}),
        StringAlias("x"),
        UnregisteredArtifact(1),
        b"",
        b"x" * (MAX_BRIDGE_PAYLOAD_OCTETS + 1),
        MAX_SAFE_INTEGER + 1,
        "\ud800",
        maximum_string + "x",
        {maximum_string + "x": None},
        [None] * (MAX_BRIDGE_COLLECTION_ITEMS + 1),
        {str(index): None for index in range(MAX_BRIDGE_COLLECTION_ITEMS + 1)},
        cycle,
        too_deep,
        excessive_nodes,
        [maximum_string] * 9,
    )
    for invalid_value in invalid_values:
        try:
            _canonical_bytes(invalid_value)
        except BridgeValidationError:
            continue
        raise BridgeValidationError("invalid bridge canonical value was accepted")
