#!/usr/bin/env python3
"""Process-isolated Python/PyNaCl adapter for the public differential corpus."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

from nacl.signing import SigningKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prototype.forwarding import (  # noqa: E402
    CLOCK_POLICY,
    MAX_MANIFEST_BYTES,
    MAX_OUTER_BYTES,
    MAX_PAYLOAD_BYTES,
    MAX_PROTECTED_BYTES,
    OUTER_LIMITS,
    PAYLOAD_LIMITS,
    PROTECTED_LIMITS,
    CarrierContext,
    EndpointProfile,
    KeyManifest,
    verify_and_commit,
)
from prototype.replay import (  # noqa: E402
    ReplayStore,
    build_recovery_authorization,
)
from prototype.strict import (  # noqa: E402
    ErrorCode,
    JsonLimits,
    PrototypeError,
    b64url_decode,
    exact_members,
    require_safe_int,
    require_sha256,
    sha256_hex,
    strict_json_loads,
)

REQUEST_SCHEMA = "ncp.prototype.signed-forwarding-node-request.v1"
RESULT_SCHEMA = "ncp.prototype.signed-forwarding-projection.v1"
RESPONSE_SCHEMA = "ncp.prototype.signed-forwarding-node-response.v1"
MAX_REQUEST_BYTES = 2_200_000
REQUEST_LIMITS = JsonLimits(MAX_REQUEST_BYTES, 8, 256, 64, 2_000_000)


def _carrier(value: Any) -> CarrierContext:
    document = exact_members(
        value,
        {
            "audience",
            "entity_id",
            "key_manifest_generation",
            "key_manifest_sha256",
            "message_class",
            "plane",
            "principal_id",
            "profile",
            "route",
            "security_state_sha256",
            "stable_core_sha256",
            "transport_role",
        },
        "carrier context",
    )
    return CarrierContext(
        principal_id=document["principal_id"],
        entity_id=document["entity_id"],
        transport_role=document["transport_role"],
        profile=document["profile"],
        route=document["route"],
        plane=document["plane"],
        message_class=document["message_class"],
        audience=document["audience"],
        stable_core_sha256=document["stable_core_sha256"],
        security_state_sha256=document["security_state_sha256"],
        key_manifest_sha256=document["key_manifest_sha256"],
        key_manifest_generation=document["key_manifest_generation"],
    )


def _endpoint(value: Any) -> EndpointProfile:
    document = exact_members(
        value,
        {
            "audience",
            "key_manifest_generation",
            "key_manifest_sha256",
            "max_clock_skew_ms",
            "max_ttl_ms",
            "message_class",
            "mode",
            "plane",
            "recovery_epoch",
            "route",
            "security_state_sha256",
            "stable_core_sha256",
        },
        "endpoint profile",
    )
    return EndpointProfile(
        route=document["route"],
        plane=document["plane"],
        message_class=document["message_class"],
        audience=document["audience"],
        stable_core_sha256=document["stable_core_sha256"],
        security_state_sha256=document["security_state_sha256"],
        key_manifest_sha256=document["key_manifest_sha256"],
        key_manifest_generation=document["key_manifest_generation"],
        recovery_epoch=document["recovery_epoch"],
        mode=document["mode"],
        max_ttl_ms=document["max_ttl_ms"],
        max_clock_skew_ms=document["max_clock_skew_ms"],
    )


def _provision_store(directory: Path, audience: str, now_utc_ms: int) -> tuple[Path, object]:
    os.chmod(directory, 0o700)
    owner = SigningKey.generate()
    owner_public = owner.verify_key.encode()
    authorization, signature = build_recovery_authorization(
        owner,
        action="initialize",
        audience=audience,
        old=None,
        new_store_id=str(uuid.uuid4()),
        new_recovery_epoch=1,
        issued_at_utc_ms=now_utc_ms,
        expires_at_utc_ms=now_utc_ms + 30_000,
    )
    path = directory / "replay.sqlite3"
    pinned = ReplayStore.provision(
        path,
        authorization,
        signature,
        owner_public_key=owner_public,
        owner_key_sha256=sha256_hex(owner_public),
        audience=audience,
        old=None,
        now_utc_ms=now_utc_ms,
    )
    return path, pinned


def _projection(
    *,
    envelope: bytes,
    manifest: KeyManifest,
    profile: EndpointProfile,
    carrier: CarrierContext,
) -> dict[str, Any]:
    outer = exact_members(
        strict_json_loads(envelope, OUTER_LIMITS),
        {"payload", "protected", "signature"},
        "flattened JWS",
    )
    protected_b64 = outer["protected"]
    payload_b64 = outer["payload"]
    signature_b64 = outer["signature"]
    protected = b64url_decode(protected_b64, maximum=MAX_PROTECTED_BYTES)
    payload = b64url_decode(payload_b64, maximum=MAX_PAYLOAD_BYTES)
    header = exact_members(
        strict_json_loads(protected, PROTECTED_LIMITS),
        {"alg", "crit", "ncp", "typ"},
        "protected header",
    )
    ncp = header["ncp"]
    entry = manifest.key(ncp["kid"])
    payload_value = strict_json_loads(payload, PAYLOAD_LIMITS, allow_floats=True)
    payload_stream: dict[str, Any] | None = None
    payload_operation: dict[str, Any] | None = None
    if profile.message_class == "command_frame":
        payload_stream = {
            "epoch": payload_value["stream"]["epoch"],
            "sequence": payload_value["stream"]["seq"],
        }
    else:
        payload_operation = {
            "expected_state_version": payload_value["operation"]["expected_state_version"],
            "operation_id": payload_value["operation"]["operation_id"],
            "request_digest": payload_value["operation"]["request_digest"],
        }
    return {
        "schema": RESULT_SCHEMA,
        "envelope_sha256": sha256_hex(envelope),
        "protected_b64": protected_b64,
        "payload_b64": payload_b64,
        "signature_b64": signature_b64,
        "signer_principal_id": entry.issuer,
        "signer_entity_id": entry.entity_id,
        "signer_role": entry.role,
        "carrier_principal_id": carrier.principal_id,
        "carrier_entity_id": carrier.entity_id,
        "carrier_transport_role": carrier.transport_role,
        "carrier_profile": carrier.profile,
        "route": profile.route,
        "plane": profile.plane,
        "message_class": profile.message_class,
        "audience": profile.audience,
        "stable_core_sha256": profile.stable_core_sha256,
        "security_state_sha256": profile.security_state_sha256,
        "kid": entry.kid,
        "key_epoch": entry.key_epoch,
        "key_manifest_generation": manifest.generation,
        "key_manifest_sha256": manifest.digest,
        "clock_policy": CLOCK_POLICY,
        "issued_at_utc_ms": ncp["issued_at_utc_ms"],
        "expires_at_utc_ms": ncp["expires_at_utc_ms"],
        "recovery_epoch": profile.recovery_epoch,
        "forwarding_epoch": ncp["forwarding_epoch"],
        "forwarding_sequence": ncp["forwarding_sequence"],
        "session_id": ncp["session_id"],
        "session_generation": ncp["session_generation"],
        "payload_sha256": sha256_hex(payload),
        "payload_stream": payload_stream,
        "payload_operation": payload_operation,
    }


def evaluate_request(request_bytes: bytes) -> dict[str, Any]:
    """Evaluate one request with a fresh replay scope and stable result schema."""

    try:
        request = exact_members(
            strict_json_loads(request_bytes, REQUEST_LIMITS),
            {
                "carrier",
                "endpoint",
                "envelope",
                "manifest",
                "manifest_sha256",
                "now_utc_ms",
                "schema",
            },
            "node verifier request",
        )
        if request["schema"] != REQUEST_SCHEMA:
            raise PrototypeError(ErrorCode.PROFILE, "node verifier request schema is unknown")
        manifest_sha256 = require_sha256(
            request["manifest_sha256"],
            "request manifest digest",
        )
        manifest_bytes = b64url_decode(request["manifest"], maximum=MAX_MANIFEST_BYTES)
        envelope = b64url_decode(request["envelope"], maximum=MAX_OUTER_BYTES)
        profile = _endpoint(request["endpoint"])
        carrier = _carrier(request["carrier"])
        now_utc_ms = require_safe_int(request["now_utc_ms"], "request current time")
        manifest = KeyManifest.parse(manifest_bytes, manifest_sha256)
        with tempfile.TemporaryDirectory() as temporary:
            path, pinned = _provision_store(Path(temporary), profile.audience, now_utc_ms)
            with ReplayStore.open(path, pinned) as replay_store:
                verify_and_commit(
                    envelope,
                    manifest=manifest,
                    profile=profile,
                    carrier=carrier,
                    replay_store=replay_store,
                    now_utc_ms=now_utc_ms,
                )
        return {
            "accepted": True,
            "projection": _projection(
                envelope=envelope,
                manifest=manifest,
                profile=profile,
                carrier=carrier,
            ),
            "schema": RESPONSE_SCHEMA,
        }
    except PrototypeError as error:
        return {
            "accepted": False,
            "error_code": str(error.code),
            "schema": RESPONSE_SCHEMA,
        }


def main() -> int:
    request = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(request) > MAX_REQUEST_BYTES:
        response = {
            "accepted": False,
            "error_code": str(ErrorCode.BOUNDS),
            "schema": RESPONSE_SCHEMA,
        }
    else:
        response = evaluate_request(request)
    sys.stdout.write(json.dumps(response, separators=(",", ":"), sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
