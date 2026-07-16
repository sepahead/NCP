"""Strict flattened-JWS forwarding verification and replay commit."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from .replay import ReplayKey, ReplayStore, validate_replay_key
from .strict import (
    ErrorCode,
    JsonLimits,
    PrototypeError,
    b64url_decode,
    b64url_encode,
    exact_members,
    require_id,
    require_literal,
    require_safe_int,
    require_sha256,
    require_uuid_v4,
    sha256_hex,
    strict_json_loads,
)

MANIFEST_SCHEMA = "ncp.prototype.forwarding-key-manifest.v1"
PROFILE = "ncp.prototype.signed-forwarding-envelope.v1"
TYPE = "ncp-forwarding-envelope+jws;v=1"
PAYLOAD_MEDIA_TYPE = "application/ncp+json;version=1.0"
CLOCK_POLICY = "unix-utc-ms-strict-v1"

MAX_OUTER_BYTES = 1_500_000
MAX_PROTECTED_BYTES = 16_384
MAX_PAYLOAD_BYTES = 1_048_576
MAX_MANIFEST_BYTES = 65_536

OUTER_LIMITS = JsonLimits(MAX_OUTER_BYTES, 3, 16, 4, MAX_OUTER_BYTES)
PROTECTED_LIMITS = JsonLimits(MAX_PROTECTED_BYTES, 6, 128, 32, 512)
MANIFEST_LIMITS = JsonLimits(MAX_MANIFEST_BYTES, 8, 2_048, 256, 512)
PAYLOAD_LIMITS = JsonLimits(MAX_PAYLOAD_BYTES, 32, 100_000, 4_096, 65_536)

_HEADER_MEMBERS = {"alg", "crit", "ncp", "typ"}
_NCP_MEMBERS = {
    "audience",
    "clock_policy",
    "expires_at_utc_ms",
    "forwarding_epoch",
    "forwarding_sequence",
    "issued_at_utc_ms",
    "issuer",
    "key_epoch",
    "key_manifest_generation",
    "key_manifest_sha256",
    "kid",
    "message_class",
    "payload_media_type",
    "payload_operation",
    "payload_sha256",
    "payload_stream",
    "plane",
    "profile",
    "recovery_epoch",
    "route",
    "security_state_sha256",
    "session_generation",
    "session_id",
    "stable_core_sha256",
}


@dataclass(frozen=True, slots=True)
class Grant:
    """One literal signer grant from the exact key manifest."""

    route: str
    plane: str
    message_class: str


@dataclass(frozen=True, slots=True)
class KeyEntry:
    """One exact Ed25519 signer entry."""

    kid: str
    public_key: bytes
    issuer: str
    entity_id: str
    role: str
    key_epoch: int
    grants: tuple[Grant, ...]


@dataclass(frozen=True, slots=True)
class KeyManifest:
    """One bounded exact-byte default-deny signer manifest snapshot."""

    generation: int
    digest: str
    exact_bytes: bytes
    audience: str
    clock_policy: str
    keys: tuple[KeyEntry, ...]

    @classmethod
    def parse(cls, exact_bytes: bytes, expected_sha256: str) -> KeyManifest:
        """Parse one content-addressed signer manifest."""

        if not 1 <= len(exact_bytes) <= MAX_MANIFEST_BYTES:
            raise PrototypeError(
                ErrorCode.BOUNDS,
                "manifest byte length is outside the profile bound",
            )
        expected_sha256 = require_sha256(expected_sha256, "manifest digest")
        if sha256_hex(exact_bytes) != expected_sha256:
            raise PrototypeError(ErrorCode.MANIFEST, "manifest exact-byte digest mismatch")
        value = exact_members(
            strict_json_loads(exact_bytes, MANIFEST_LIMITS),
            {
                "audience",
                "clock_policy",
                "default_deny",
                "generation",
                "keys",
                "schema",
            },
            "key manifest",
        )
        if (
            value["schema"] != MANIFEST_SCHEMA
            or value["default_deny"] is not True
            or value["clock_policy"] != CLOCK_POLICY
        ):
            raise PrototypeError(ErrorCode.MANIFEST, "manifest profile is unknown or permissive")
        generation = require_safe_int(value["generation"], "manifest generation", positive=True)
        audience = require_id(value["audience"], "manifest audience")
        raw_keys = value["keys"]
        if not isinstance(raw_keys, list) or not 1 <= len(raw_keys) <= 64:
            raise PrototypeError(ErrorCode.MANIFEST, "manifest key count is outside 1..=64")

        keys: list[KeyEntry] = []
        kids: set[str] = set()
        issuer_epochs: set[tuple[str, int]] = set()
        issuer_identity: dict[str, tuple[str, str]] = {}
        entity_issuer: dict[str, str] = {}
        for index, raw in enumerate(raw_keys):
            entry = exact_members(
                raw,
                {
                    "entity_id",
                    "grants",
                    "issuer",
                    "key_epoch",
                    "kid",
                    "public_key",
                    "role",
                },
                f"manifest keys[{index}]",
            )
            kid = require_sha256(entry["kid"], f"manifest keys[{index}].kid")
            public_key = b64url_decode(entry["public_key"], maximum=32)
            if len(public_key) != 32 or sha256_hex(public_key) != kid:
                raise PrototypeError(
                    ErrorCode.MANIFEST,
                    "manifest public key does not match its content-addressed kid",
                )
            issuer = require_id(entry["issuer"], f"manifest keys[{index}].issuer")
            entity_id = require_id(entry["entity_id"], f"manifest keys[{index}].entity_id")
            role = entry["role"]
            if role not in {"commander", "body", "observer", "operator"}:
                raise PrototypeError(ErrorCode.MANIFEST, "manifest signer role is unknown")
            key_epoch = require_safe_int(
                entry["key_epoch"],
                f"manifest keys[{index}].key_epoch",
                positive=True,
            )
            raw_grants = entry["grants"]
            if not isinstance(raw_grants, list) or not 1 <= len(raw_grants) <= 32:
                raise PrototypeError(ErrorCode.MANIFEST, "manifest grant count is outside 1..=32")
            grants: list[Grant] = []
            seen_grants: set[tuple[str, str, str]] = set()
            for grant_index, raw_grant in enumerate(raw_grants):
                grant = exact_members(
                    raw_grant,
                    {"message_class", "plane", "route"},
                    f"manifest keys[{index}].grants[{grant_index}]",
                )
                route = require_literal(grant["route"], "manifest grant route", 256)
                plane = grant["plane"]
                if plane not in {"control", "perception", "action", "observation"}:
                    raise PrototypeError(ErrorCode.MANIFEST, "manifest grant plane is unknown")
                message_class = require_literal(
                    grant["message_class"],
                    "manifest grant message class",
                    64,
                )
                grant_key = (route, plane, message_class)
                if grant_key in seen_grants:
                    raise PrototypeError(ErrorCode.MANIFEST, "manifest contains a duplicate grant")
                seen_grants.add(grant_key)
                grants.append(Grant(*grant_key))
            identity = (entity_id, role)
            if issuer in issuer_identity and issuer_identity[issuer] != identity:
                raise PrototypeError(
                    ErrorCode.MANIFEST,
                    "one issuer cannot change entity or role across key epochs",
                )
            if entity_id in entity_issuer and entity_issuer[entity_id] != issuer:
                raise PrototypeError(
                    ErrorCode.MANIFEST,
                    "one entity cannot belong to multiple signer issuers",
                )
            if kid in kids or (issuer, key_epoch) in issuer_epochs:
                raise PrototypeError(
                    ErrorCode.MANIFEST,
                    "manifest kid and issuer/key-epoch pairs must be unique",
                )
            kids.add(kid)
            issuer_epochs.add((issuer, key_epoch))
            issuer_identity[issuer] = identity
            entity_issuer[entity_id] = issuer
            keys.append(
                KeyEntry(
                    kid,
                    public_key,
                    issuer,
                    entity_id,
                    role,
                    key_epoch,
                    tuple(grants),
                )
            )
        return cls(
            generation,
            expected_sha256,
            bytes(exact_bytes),
            audience,
            CLOCK_POLICY,
            tuple(keys),
        )

    def key(self, kid: str) -> KeyEntry:
        """Return one exact key entry without fallback."""

        for entry in self.keys:
            if entry.kid == kid:
                return entry
        raise PrototypeError(ErrorCode.MANIFEST, "kid is absent from the current manifest")


@dataclass(frozen=True, slots=True)
class CarrierContext:
    """Simulated verified-A carrier facts used only for B-over-A congruence."""

    principal_id: str
    entity_id: str
    transport_role: str
    profile: str
    route: str
    plane: str
    message_class: str
    audience: str
    stable_core_sha256: str
    security_state_sha256: str
    key_manifest_sha256: str
    key_manifest_generation: int

    def validate(self) -> None:
        """Reject any carrier fact that could widen or negotiate the profile."""

        require_id(self.principal_id, "carrier principal_id")
        require_id(self.entity_id, "carrier entity_id")
        if self.transport_role != "forwarder" or self.profile != "b-over-a-forwarding":
            raise PrototypeError(ErrorCode.PROFILE, "carrier is not pinned to forwarding-only")
        require_literal(self.route, "carrier route", 256)
        if self.plane not in {"control", "perception", "action", "observation"}:
            raise PrototypeError(ErrorCode.PROFILE, "carrier plane is unknown")
        require_literal(self.message_class, "carrier message class", 64)
        require_id(self.audience, "carrier audience")
        require_sha256(self.stable_core_sha256, "carrier stable-core digest")
        require_sha256(self.security_state_sha256, "carrier security-state digest")
        require_sha256(self.key_manifest_sha256, "carrier key-manifest digest")
        require_safe_int(
            self.key_manifest_generation,
            "carrier key-manifest generation",
            positive=True,
        )


@dataclass(frozen=True, slots=True)
class EndpointProfile:
    """Receiver-pinned non-negotiable forwarding endpoint profile."""

    route: str
    plane: str
    message_class: str
    audience: str
    stable_core_sha256: str
    security_state_sha256: str
    key_manifest_sha256: str
    key_manifest_generation: int
    recovery_epoch: int
    mode: str = "b-over-a-forwarding"
    max_ttl_ms: int = 5_000
    max_clock_skew_ms: int = 1_000

    def validate(self) -> None:
        """Validate every locally pinned endpoint field."""

        require_literal(self.route, "endpoint route", 256)
        if self.mode != "b-over-a-forwarding":
            raise PrototypeError(ErrorCode.PROFILE, "endpoint is not forwarding-only")
        if self.plane not in {"control", "perception", "action", "observation"}:
            raise PrototypeError(ErrorCode.PROFILE, "endpoint plane is unknown")
        if self.message_class not in {"command_frame", "step_request"}:
            raise PrototypeError(ErrorCode.PROFILE, "prototype message class is unsupported")
        require_id(self.audience, "endpoint audience")
        require_sha256(self.stable_core_sha256, "endpoint stable-core digest")
        require_sha256(self.security_state_sha256, "endpoint security-state digest")
        require_sha256(self.key_manifest_sha256, "endpoint key-manifest digest")
        require_safe_int(
            self.key_manifest_generation,
            "endpoint key-manifest generation",
            positive=True,
        )
        require_safe_int(self.recovery_epoch, "endpoint recovery_epoch", positive=True)
        require_safe_int(self.max_ttl_ms, "endpoint maximum TTL", positive=True)
        require_safe_int(self.max_clock_skew_ms, "endpoint clock skew")


@dataclass(frozen=True, slots=True)
class VerifiedForwardingContext:
    """Authenticated signer and exact routing facts that grant no NCP authority."""

    signer_principal_id: str
    signer_entity_id: str
    signer_role: str
    carrier_principal_id: str
    carrier_entity_id: str
    carrier_transport_role: str
    carrier_profile: str
    route: str
    plane: str
    message_class: str
    audience: str
    stable_core_sha256: str
    security_state_sha256: str
    kid: str
    key_epoch: int
    key_manifest_generation: int
    key_manifest_sha256: str
    recovery_epoch: int
    forwarding_epoch: str
    forwarding_sequence: int
    session_id: str
    session_generation: str
    payload_sha256: str


@dataclass(frozen=True, slots=True)
class VerifiedForwardedMessage:
    """Immutable verified context paired with the exact signed payload bytes."""

    context: VerifiedForwardingContext
    payload: bytes


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def build_envelope(
    signing_key: SigningKey,
    *,
    ncp_context: dict[str, Any],
    payload: bytes,
) -> bytes:
    """Build a flattened prototype JWS for tests without retaining a private key."""

    protected = _canonical_json(
        {
            "alg": "Ed25519",
            "crit": ["ncp"],
            "ncp": ncp_context,
            "typ": TYPE,
        }
    )
    protected_b64 = b64url_encode(protected)
    payload_b64 = b64url_encode(payload)
    signature = signing_key.sign(f"{protected_b64}.{payload_b64}".encode("ascii")).signature
    return _canonical_json(
        {
            "payload": payload_b64,
            "protected": protected_b64,
            "signature": b64url_encode(signature),
        }
    )


def _payload_semantics(payload: bytes, ncp: dict[str, Any], profile: EndpointProfile) -> None:
    value = strict_json_loads(payload, PAYLOAD_LIMITS, allow_floats=True)
    if not isinstance(value, dict):
        raise PrototypeError(ErrorCode.PAYLOAD, "NCP payload is not an object")
    if value.get("ncp_version") != "1.0" or value.get("kind") != profile.message_class:
        raise PrototypeError(ErrorCode.PAYLOAD, "NCP version or message class mismatch")
    if value.get("session_id") != ncp["session_id"]:
        raise PrototypeError(ErrorCode.PAYLOAD, "payload session_id mismatch")
    session = value.get("session")
    if not isinstance(session, dict) or session.get("generation") != ncp["session_generation"]:
        raise PrototypeError(ErrorCode.PAYLOAD, "payload session generation mismatch")

    if profile.message_class == "command_frame":
        if ncp["payload_operation"] is not None:
            raise PrototypeError(ErrorCode.PAYLOAD, "streamed command cannot bind an operation")
        protected_stream = exact_members(
            ncp["payload_stream"],
            {"epoch", "sequence"},
            "protected payload_stream",
        )
        stream = value.get("stream")
        if not isinstance(stream, dict):
            raise PrototypeError(ErrorCode.PAYLOAD, "command payload has no stream position")
        epoch = require_uuid_v4(stream.get("epoch"), "payload stream epoch")
        sequence = require_safe_int(stream.get("seq"), "payload stream sequence", positive=True)
        if protected_stream["epoch"] != epoch or protected_stream["sequence"] != sequence:
            raise PrototypeError(ErrorCode.PAYLOAD, "protected stream binding mismatch")
    elif profile.message_class == "step_request":
        if ncp["payload_stream"] is not None:
            raise PrototypeError(
                ErrorCode.PAYLOAD, "operation request cannot bind a payload stream"
            )
        protected_operation = exact_members(
            ncp["payload_operation"],
            {"expected_state_version", "operation_id", "request_digest"},
            "protected payload_operation",
        )
        operation = value.get("operation")
        if not isinstance(operation, dict):
            raise PrototypeError(ErrorCode.PAYLOAD, "step request has no operation context")
        operation_id = require_uuid_v4(operation.get("operation_id"), "payload operation_id")
        expected_state_version = require_safe_int(
            operation.get("expected_state_version"),
            "payload expected_state_version",
        )
        request_digest = require_sha256(
            operation.get("request_digest"),
            "payload request_digest",
        )
        if operation.get("session_epoch") != ncp["session_generation"]:
            raise PrototypeError(ErrorCode.PAYLOAD, "operation session generation mismatch")
        if protected_operation != {
            "expected_state_version": expected_state_version,
            "operation_id": operation_id,
            "request_digest": request_digest,
        }:
            raise PrototypeError(ErrorCode.PAYLOAD, "protected operation binding mismatch")


def _validate_context(
    ncp: dict[str, Any],
    profile: EndpointProfile,
    carrier: CarrierContext,
    manifest: KeyManifest,
    now_utc_ms: int,
) -> KeyEntry:
    profile.validate()
    carrier.validate()
    if (
        carrier.route != profile.route
        or carrier.plane != profile.plane
        or carrier.message_class != profile.message_class
        or carrier.audience != profile.audience
        or carrier.stable_core_sha256 != profile.stable_core_sha256
        or carrier.security_state_sha256 != profile.security_state_sha256
        or carrier.key_manifest_sha256 != profile.key_manifest_sha256
        or carrier.key_manifest_generation != profile.key_manifest_generation
    ):
        raise PrototypeError(ErrorCode.PROFILE, "carrier and endpoint profile are incongruent")
    if (
        manifest.digest != profile.key_manifest_sha256
        or manifest.generation != profile.key_manifest_generation
        or manifest.audience != profile.audience
    ):
        raise PrototypeError(ErrorCode.MANIFEST, "current manifest and endpoint are incongruent")

    if ncp["profile"] != PROFILE or ncp["payload_media_type"] != PAYLOAD_MEDIA_TYPE:
        raise PrototypeError(ErrorCode.PROFILE, "forwarding profile or media type mismatch")
    exact_pairs = {
        "route": profile.route,
        "plane": profile.plane,
        "message_class": profile.message_class,
        "audience": profile.audience,
        "stable_core_sha256": profile.stable_core_sha256,
        "security_state_sha256": profile.security_state_sha256,
        "key_manifest_sha256": profile.key_manifest_sha256,
        "key_manifest_generation": profile.key_manifest_generation,
        "recovery_epoch": profile.recovery_epoch,
        "clock_policy": CLOCK_POLICY,
    }
    for field, expected in exact_pairs.items():
        if ncp[field] != expected:
            raise PrototypeError(ErrorCode.PROFILE, f"protected {field} mismatch")

    kid = require_sha256(ncp["kid"], "protected kid")
    entry = manifest.key(kid)
    issuer = require_id(ncp["issuer"], "protected issuer")
    key_epoch = require_safe_int(ncp["key_epoch"], "protected key_epoch", positive=True)
    if issuer != entry.issuer or key_epoch != entry.key_epoch:
        raise PrototypeError(ErrorCode.MANIFEST, "protected signer or key epoch mismatch")
    if entry.issuer == carrier.principal_id or entry.entity_id == carrier.entity_id:
        raise PrototypeError(
            ErrorCode.PROFILE,
            "operation signer principal/entity cannot equal its carrier",
        )
    if entry.role != "commander":
        raise PrototypeError(ErrorCode.PROFILE, "prototype command signer is not a commander")
    if Grant(profile.route, profile.plane, profile.message_class) not in entry.grants:
        raise PrototypeError(ErrorCode.MANIFEST, "signer lacks the exact endpoint grant")

    issued = require_safe_int(ncp["issued_at_utc_ms"], "protected issued_at")
    expires = require_safe_int(ncp["expires_at_utc_ms"], "protected expires_at")
    if expires <= issued or expires - issued > profile.max_ttl_ms:
        raise PrototypeError(ErrorCode.PROFILE, "forwarding envelope TTL is invalid")
    if (
        now_utc_ms + profile.max_clock_skew_ms < issued
        or now_utc_ms - profile.max_clock_skew_ms > expires
    ):
        raise PrototypeError(ErrorCode.PROFILE, "forwarding envelope is not currently valid")
    return entry


def verify_and_commit(
    envelope: bytes,
    *,
    manifest: KeyManifest,
    profile: EndpointProfile,
    carrier: CarrierContext,
    replay_store: ReplayStore,
    now_utc_ms: int,
) -> VerifiedForwardedMessage:
    """Verify one exact flattened JWS and durably commit replay before handoff."""

    outer = exact_members(
        strict_json_loads(envelope, OUTER_LIMITS),
        {"payload", "protected", "signature"},
        "flattened JWS",
    )
    if not all(isinstance(outer[field], str) for field in outer):
        raise PrototypeError(ErrorCode.PROFILE, "flattened JWS members must be strings")
    protected_b64 = outer["protected"]
    payload_b64 = outer["payload"]
    signature_b64 = outer["signature"]
    protected_bytes = b64url_decode(protected_b64, maximum=MAX_PROTECTED_BYTES)
    payload = b64url_decode(payload_b64, maximum=MAX_PAYLOAD_BYTES)
    signature = b64url_decode(signature_b64, maximum=64)
    if len(signature) != 64:
        raise PrototypeError(ErrorCode.CRYPTO, "Ed25519 signature is not exactly 64 bytes")

    header = exact_members(
        strict_json_loads(protected_bytes, PROTECTED_LIMITS),
        _HEADER_MEMBERS,
        "protected header",
    )
    if header["alg"] != "Ed25519" or header["typ"] != TYPE or header["crit"] != ["ncp"]:
        raise PrototypeError(ErrorCode.PROFILE, "algorithm, type, or critical profile mismatch")
    ncp = exact_members(header["ncp"], _NCP_MEMBERS, "protected ncp context")
    entry = _validate_context(
        ncp,
        profile,
        carrier,
        manifest,
        require_safe_int(now_utc_ms, "current time"),
    )

    signing_input = f"{protected_b64}.{payload_b64}".encode("ascii")
    try:
        VerifyKey(entry.public_key).verify(signing_input, signature)
    except (BadSignatureError, ValueError) as error:
        raise PrototypeError(ErrorCode.CRYPTO, "strict Ed25519 verification rejected") from error

    payload_digest = sha256_hex(payload)
    if require_sha256(ncp["payload_sha256"], "protected payload digest") != payload_digest:
        raise PrototypeError(ErrorCode.PAYLOAD, "protected payload digest mismatch")
    require_id(ncp["session_id"], "protected session_id")
    require_uuid_v4(ncp["session_generation"], "protected session_generation")
    require_uuid_v4(ncp["forwarding_epoch"], "protected forwarding_epoch")
    forwarding_sequence = require_safe_int(
        ncp["forwarding_sequence"],
        "protected forwarding_sequence",
        positive=True,
    )
    _payload_semantics(payload, ncp, profile)

    replay_key = validate_replay_key(
        ReplayKey(
            signer=entry.issuer,
            receiver=profile.audience,
            route=profile.route,
            plane=profile.plane,
            message_class=profile.message_class,
            session_id=ncp["session_id"],
            session_generation=ncp["session_generation"],
            forwarding_epoch=ncp["forwarding_epoch"],
            key_epoch=entry.key_epoch,
            recovery_epoch=profile.recovery_epoch,
        )
    )
    replay_store.commit_sequence(replay_key, forwarding_sequence)
    return VerifiedForwardedMessage(
        VerifiedForwardingContext(
            signer_principal_id=entry.issuer,
            signer_entity_id=entry.entity_id,
            signer_role=entry.role,
            carrier_principal_id=carrier.principal_id,
            carrier_entity_id=carrier.entity_id,
            carrier_transport_role=carrier.transport_role,
            carrier_profile=carrier.profile,
            route=profile.route,
            plane=profile.plane,
            message_class=profile.message_class,
            audience=profile.audience,
            stable_core_sha256=profile.stable_core_sha256,
            security_state_sha256=profile.security_state_sha256,
            kid=entry.kid,
            key_epoch=entry.key_epoch,
            key_manifest_generation=manifest.generation,
            key_manifest_sha256=manifest.digest,
            recovery_epoch=profile.recovery_epoch,
            forwarding_epoch=ncp["forwarding_epoch"],
            forwarding_sequence=forwarding_sequence,
            session_id=ncp["session_id"],
            session_generation=ncp["session_generation"],
            payload_sha256=payload_digest,
        ),
        bytes(payload),
    )


def decimal_to_json_number(value: Decimal) -> int | float:
    """Test helper for comparing parsed NCP numeric values without signing them."""

    return int(value) if value == value.to_integral_value() else float(value)
