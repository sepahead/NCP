"""Runtime-only keys and exact NCP inputs for prototype tests."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nacl.signing import SigningKey

from prototype.forwarding import (
    CLOCK_POLICY,
    MANIFEST_SCHEMA,
    PAYLOAD_MEDIA_TYPE,
    PROFILE,
    CarrierContext,
    EndpointProfile,
    KeyManifest,
    build_envelope,
)
from prototype.replay import (
    PinnedReplayState,
    ReplayStore,
    build_recovery_authorization,
)
from prototype.strict import b64url_encode, sha256_hex

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[2]
NOW = 1_700_000_000_000
AUDIENCE = "crebain-body-1"
ISSUER = "controller-principal-1"
ENTITY = "pid-controller-1"
CARRIER = "ingress-forwarder-1"
CARRIER_ENTITY = "ingress-process-1"
ROUTE = "ncp/plant/body-1/command"
STABLE_CORE = "1" * 64
SECURITY_STATE = "2" * 64
FORWARDING_EPOCH = "30000000-0000-4000-8000-000000000003"


@dataclass(slots=True)
class Material:
    signer: SigningKey
    owner: SigningKey
    manifest_bytes: bytes
    manifest: KeyManifest
    profile: EndpointProfile
    carrier: CarrierContext
    payload: bytes
    ncp_context: dict[str, Any]
    envelope: bytes


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def ncp_payload(message_class: str) -> bytes:
    path = REPOSITORY / "conformance" / "vectors" / f"{message_class}.json"
    return path.read_bytes()


def manifest_for(signing_key: SigningKey, message_class: str) -> tuple[bytes, KeyManifest]:
    public_key = signing_key.verify_key.encode()
    kid = sha256_hex(public_key)
    exact = canonical_json(
        {
            "audience": AUDIENCE,
            "clock_policy": CLOCK_POLICY,
            "default_deny": True,
            "generation": 1,
            "keys": [
                {
                    "entity_id": ENTITY,
                    "grants": [
                        {
                            "message_class": message_class,
                            "plane": "control",
                            "route": ROUTE,
                        }
                    ],
                    "issuer": ISSUER,
                    "key_epoch": 1,
                    "kid": kid,
                    "public_key": b64url_encode(public_key),
                    "role": "commander",
                }
            ],
            "schema": MANIFEST_SCHEMA,
        }
    )
    return exact, KeyManifest.parse(exact, sha256_hex(exact))


def protected_context(
    material_manifest: KeyManifest,
    payload: bytes,
    message_class: str,
    *,
    recovery_epoch: int = 1,
    forwarding_sequence: int = 1,
) -> dict[str, Any]:
    value = json.loads(payload)
    stream: dict[str, Any] | None = None
    operation: dict[str, Any] | None = None
    if message_class == "command_frame":
        stream = {
            "epoch": value["stream"]["epoch"],
            "sequence": value["stream"]["seq"],
        }
    elif message_class == "step_request":
        operation = {
            "expected_state_version": value["operation"]["expected_state_version"],
            "operation_id": value["operation"]["operation_id"],
            "request_digest": value["operation"]["request_digest"],
        }
    return {
        "audience": AUDIENCE,
        "clock_policy": CLOCK_POLICY,
        "expires_at_utc_ms": NOW + 4_000,
        "forwarding_epoch": FORWARDING_EPOCH,
        "forwarding_sequence": forwarding_sequence,
        "issued_at_utc_ms": NOW,
        "issuer": ISSUER,
        "key_epoch": 1,
        "key_manifest_generation": material_manifest.generation,
        "key_manifest_sha256": material_manifest.digest,
        "kid": material_manifest.keys[0].kid,
        "message_class": message_class,
        "payload_media_type": PAYLOAD_MEDIA_TYPE,
        "payload_operation": operation,
        "payload_sha256": sha256_hex(payload),
        "payload_stream": stream,
        "plane": "control",
        "profile": PROFILE,
        "recovery_epoch": recovery_epoch,
        "route": ROUTE,
        "security_state_sha256": SECURITY_STATE,
        "session_generation": value["session"]["generation"],
        "session_id": value["session_id"],
        "stable_core_sha256": STABLE_CORE,
    }


def material(
    message_class: str = "command_frame",
    *,
    recovery_epoch: int = 1,
    forwarding_sequence: int = 1,
) -> Material:
    signer = SigningKey.generate()
    owner = SigningKey.generate()
    manifest_bytes, manifest = manifest_for(signer, message_class)
    payload = ncp_payload(message_class)
    context = protected_context(
        manifest,
        payload,
        message_class,
        recovery_epoch=recovery_epoch,
        forwarding_sequence=forwarding_sequence,
    )
    profile = EndpointProfile(
        route=ROUTE,
        plane="control",
        message_class=message_class,
        audience=AUDIENCE,
        stable_core_sha256=STABLE_CORE,
        security_state_sha256=SECURITY_STATE,
        key_manifest_sha256=manifest.digest,
        key_manifest_generation=manifest.generation,
        recovery_epoch=recovery_epoch,
    )
    carrier = CarrierContext(
        principal_id=CARRIER,
        entity_id=CARRIER_ENTITY,
        transport_role="forwarder",
        profile="b-over-a-forwarding",
        route=ROUTE,
        plane="control",
        message_class=message_class,
        audience=AUDIENCE,
        stable_core_sha256=STABLE_CORE,
        security_state_sha256=SECURITY_STATE,
        key_manifest_sha256=manifest.digest,
        key_manifest_generation=manifest.generation,
    )
    return Material(
        signer,
        owner,
        manifest_bytes,
        manifest,
        profile,
        carrier,
        payload,
        context,
        build_envelope(signer, ncp_context=context, payload=payload),
    )


def initialize_store(
    directory: Path,
    owner: SigningKey,
    *,
    old: PinnedReplayState | None = None,
    new_epoch: int = 1,
    path: Path | None = None,
) -> tuple[Path, PinnedReplayState]:
    os.chmod(directory, 0o700)
    path = path or directory / "replay.sqlite3"
    authorization, signature = build_recovery_authorization(
        owner,
        action="recover" if old else "initialize",
        audience=AUDIENCE,
        old=old,
        new_store_id=str(uuid.uuid4()),
        new_recovery_epoch=new_epoch,
        issued_at_utc_ms=NOW,
        expires_at_utc_ms=NOW + 30_000,
    )
    pinned = ReplayStore.provision(
        path,
        authorization,
        signature,
        owner_public_key=owner.verify_key.encode(),
        owner_key_sha256=sha256_hex(owner.verify_key.encode()),
        audience=AUDIENCE,
        old=old,
        now_utc_ms=NOW,
    )
    return path, pinned


def resigned(
    material_value: Material, context: dict[str, Any], payload: bytes | None = None
) -> bytes:
    return build_envelope(
        material_value.signer,
        ncp_context=context,
        payload=material_value.payload if payload is None else payload,
    )
