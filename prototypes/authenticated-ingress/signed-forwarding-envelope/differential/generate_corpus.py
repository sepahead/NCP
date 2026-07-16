#!/usr/bin/env python3
"""Generate a public-only signed corpus; runtime private keys are discarded."""

from __future__ import annotations

import argparse
import base64
import copy
import json
import sys
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any

from nacl.signing import SigningKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from python_adapter import evaluate_request  # noqa: E402

from prototype.forwarding import (  # noqa: E402
    KeyManifest,
    build_envelope,
)
from prototype.strict import b64url_decode, b64url_encode, sha256_hex  # noqa: E402
from tests.common import (  # noqa: E402
    NOW,
    Material,
    canonical_json,
    material,
    resigned,
)

CORPUS_SCHEMA = "ncp.prototype.signed-forwarding-differential-corpus.v1"


def request_document(
    value: Material,
    *,
    envelope: bytes | None = None,
    manifest_bytes: bytes | None = None,
    profile: object | None = None,
    carrier: object | None = None,
) -> dict[str, Any]:
    exact_manifest = value.manifest_bytes if manifest_bytes is None else manifest_bytes
    endpoint = value.profile if profile is None else profile
    carrier_value = value.carrier if carrier is None else carrier
    return {
        "carrier": {
            "audience": carrier_value.audience,
            "entity_id": carrier_value.entity_id,
            "key_manifest_generation": carrier_value.key_manifest_generation,
            "key_manifest_sha256": carrier_value.key_manifest_sha256,
            "message_class": carrier_value.message_class,
            "plane": carrier_value.plane,
            "principal_id": carrier_value.principal_id,
            "profile": carrier_value.profile,
            "route": carrier_value.route,
            "security_state_sha256": carrier_value.security_state_sha256,
            "stable_core_sha256": carrier_value.stable_core_sha256,
            "transport_role": carrier_value.transport_role,
        },
        "endpoint": {
            "audience": endpoint.audience,
            "key_manifest_generation": endpoint.key_manifest_generation,
            "key_manifest_sha256": endpoint.key_manifest_sha256,
            "max_clock_skew_ms": endpoint.max_clock_skew_ms,
            "max_ttl_ms": endpoint.max_ttl_ms,
            "message_class": endpoint.message_class,
            "mode": endpoint.mode,
            "plane": endpoint.plane,
            "recovery_epoch": endpoint.recovery_epoch,
            "route": endpoint.route,
            "security_state_sha256": endpoint.security_state_sha256,
            "stable_core_sha256": endpoint.stable_core_sha256,
        },
        "envelope": b64url_encode(value.envelope if envelope is None else envelope),
        "manifest": b64url_encode(exact_manifest),
        "manifest_sha256": sha256_hex(exact_manifest),
        "now_utc_ms": NOW,
        "schema": "ncp.prototype.signed-forwarding-node-request.v1",
    }


def request_bytes(value: Material, **kwargs: Any) -> bytes:
    return canonical_json(request_document(value, **kwargs))


def custom_header(value: Material, header: dict[str, Any], payload: bytes | None = None) -> bytes:
    exact_payload = value.payload if payload is None else payload
    protected_b64 = b64url_encode(canonical_json(header))
    payload_b64 = b64url_encode(exact_payload)
    signature = value.signer.sign(f"{protected_b64}.{payload_b64}".encode("ascii")).signature
    return canonical_json(
        {
            "payload": payload_b64,
            "protected": protected_b64,
            "signature": b64url_encode(signature),
        }
    )


def outer(envelope: bytes) -> dict[str, str]:
    return json.loads(envelope)


def protected(envelope: bytes) -> dict[str, Any]:
    return json.loads(b64url_decode(outer(envelope)["protected"], maximum=16_384))


def noncanonical_same_bytes(token: str) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    padding = "=" * ((4 - len(token) % 4) % 4)
    decoded = base64.b64decode(token + padding, altchars=b"-_", validate=True)
    for candidate in alphabet:
        mutant = token[:-1] + candidate
        if mutant == token:
            continue
        try:
            value = base64.b64decode(mutant + padding, altchars=b"-_", validate=True)
        except ValueError:
            continue
        if value == decoded:
            return mutant
    raise ValueError("token has no alternate trailing-bit encoding")


def add_case(cases: list[dict[str, Any]], identifier: str, note: str, request: bytes) -> None:
    response = evaluate_request(request)
    expected: dict[str, Any] = {"accepted": response["accepted"]}
    if response["accepted"]:
        exact_projection = canonical_json(response["projection"])
        expected["projection_sha256"] = sha256(exact_projection).hexdigest()
    else:
        expected["error_code"] = response["error_code"]
    cases.append(
        {
            "expected": expected,
            "id": identifier,
            "note": note,
            "request_b64": b64url_encode(request),
            "request_sha256": sha256_hex(request),
        }
    )


def generate() -> dict[str, Any]:
    command = material("command_frame")
    step = material("step_request")
    cases: list[dict[str, Any]] = []

    add_case(cases, "accept-command", "Python-signed command_frame", request_bytes(command))
    add_case(cases, "accept-step", "Python-signed step_request", request_bytes(step))
    maximum_context = copy.deepcopy(command.ncp_context)
    maximum_context["forwarding_sequence"] = 9_007_199_254_740_991
    add_case(
        cases,
        "accept-maximum-safe-forwarding-integer",
        "maximum interoperable forwarding sequence",
        request_bytes(command, envelope=resigned(command, maximum_context)),
    )

    parsed_outer = outer(command.envelope)
    duplicate_outer = (
        '{"payload":"'
        + parsed_outer["payload"]
        + '","payload":"'
        + parsed_outer["payload"]
        + '","protected":"'
        + parsed_outer["protected"]
        + '","signature":"'
        + parsed_outer["signature"]
        + '"}'
    ).encode("ascii")
    add_case(
        cases,
        "reject-duplicate-envelope-member",
        "duplicate outer payload member",
        request_bytes(command, envelope=duplicate_outer),
    )
    add_case(
        cases,
        "reject-escaped-duplicate-request-member",
        "duplicate request name after escape decoding",
        b'{"schema":"x","sch\\u0065ma":"y"}',
    )
    add_case(
        cases,
        "reject-request-bom",
        "UTF-8 BOM before request",
        b"\xef\xbb\xbf" + request_bytes(command),
    )
    add_case(cases, "reject-request-invalid-utf8", "invalid request UTF-8", b"\xff")

    padded = request_document(command)
    padded["envelope"] += "="
    add_case(
        cases,
        "reject-padded-request-base64url",
        "padded request envelope base64url",
        canonical_json(padded),
    )
    trailing_bits = request_document(command)
    trailing_bits["envelope"] = noncanonical_same_bytes(trailing_bits["envelope"])
    add_case(
        cases,
        "reject-base64url-trailing-bits",
        "request envelope has a noncanonical final base64url character",
        canonical_json(trailing_bits),
    )

    unsafe_outer = outer(command.envelope)
    protected_source = b64url_decode(
        unsafe_outer["protected"],
        maximum=16_384,
    ).decode("ascii")
    numeric_cases = [
        (
            "reject-unsafe-forwarding-integer",
            "protected integer exceeds interoperable safe range",
            "9007199254740992",
        ),
        (
            "reject-negative-zero-forwarding-integer",
            "protected integer is negative zero",
            "-0",
        ),
        (
            "reject-fractional-forwarding-integer",
            "protected integer is fractional",
            "1.0",
        ),
        (
            "reject-exponent-forwarding-integer",
            "protected integer uses exponent syntax",
            "1e0",
        ),
    ]
    for identifier, note, token in numeric_cases:
        numeric_outer = copy.deepcopy(unsafe_outer)
        numeric_protected = protected_source.replace(
            '"forwarding_sequence":1',
            f'"forwarding_sequence":{token}',
        ).encode("ascii")
        numeric_outer["protected"] = b64url_encode(numeric_protected)
        add_case(
            cases,
            identifier,
            note,
            request_bytes(command, envelope=canonical_json(numeric_outer)),
        )

    wrong_algorithm = protected(command.envelope)
    wrong_algorithm["alg"] = "EdDSA"
    add_case(
        cases,
        "reject-algorithm-substitution",
        "EdDSA alias is outside the exact profile",
        request_bytes(command, envelope=custom_header(command, wrong_algorithm)),
    )

    remote_key = protected(command.envelope)
    remote_key["jwk"] = {"kty": "OKP"}
    add_case(
        cases,
        "reject-unprotected-key-selection",
        "protected header contains an attacker-selected key",
        request_bytes(command, envelope=custom_header(command, remote_key)),
    )

    changed_payload_outer = outer(command.envelope)
    changed_payload = bytearray(command.payload)
    changed_payload[-2] ^= 1
    changed_payload_outer["payload"] = b64url_encode(bytes(changed_payload))
    add_case(
        cases,
        "reject-changed-payload-bytes",
        "payload changes without a new signature",
        request_bytes(command, envelope=canonical_json(changed_payload_outer)),
    )

    scalar_outer = outer(command.envelope)
    signature = bytearray(b64url_decode(scalar_outer["signature"], maximum=64))
    order = 2**252 + 27742317777372353535851937790883648493
    scalar = int.from_bytes(signature[32:], "little") + order
    signature[32:] = scalar.to_bytes(32, "little")
    scalar_outer["signature"] = b64url_encode(signature)
    add_case(
        cases,
        "reject-noncanonical-ed25519-s",
        "signature scalar S plus the group order",
        request_bytes(command, envelope=canonical_json(scalar_outer)),
    )

    manifest_document = json.loads(command.manifest_bytes)
    extra_manifest = copy.deepcopy(manifest_document)
    extra_manifest["keys"][0]["extra"] = True
    add_case(
        cases,
        "reject-manifest-extra-field",
        "manifest key entry has an unknown member",
        request_bytes(command, manifest_bytes=canonical_json(extra_manifest)),
    )

    wildcard_manifest = copy.deepcopy(manifest_document)
    wildcard_manifest["keys"][0]["grants"][0]["route"] = "ncp/*"
    add_case(
        cases,
        "reject-manifest-wildcard",
        "manifest grant attempts wildcard widening",
        request_bytes(command, manifest_bytes=canonical_json(wildcard_manifest)),
    )

    nonascii_route = "ncp/plánt/body-1/command"
    nonascii_manifest_document = copy.deepcopy(manifest_document)
    nonascii_manifest_document["keys"][0]["grants"][0]["route"] = nonascii_route
    nonascii_manifest_bytes = canonical_json(nonascii_manifest_document)
    nonascii_digest = sha256_hex(nonascii_manifest_bytes)
    nonascii_context = copy.deepcopy(command.ncp_context)
    nonascii_context["route"] = nonascii_route
    nonascii_context["key_manifest_sha256"] = nonascii_digest
    nonascii_profile = replace(
        command.profile,
        route=nonascii_route,
        key_manifest_sha256=nonascii_digest,
    )
    nonascii_carrier = replace(
        command.carrier,
        route=nonascii_route,
        key_manifest_sha256=nonascii_digest,
    )
    add_case(
        cases,
        "reject-nonascii-route-literal",
        "route literal contains a non-ASCII code point",
        request_bytes(
            command,
            envelope=resigned(command, nonascii_context),
            manifest_bytes=nonascii_manifest_bytes,
            profile=nonascii_profile,
            carrier=nonascii_carrier,
        ),
    )

    zero_manifest_document = copy.deepcopy(manifest_document)
    zero_key = bytes(32)
    zero_manifest_document["keys"][0]["public_key"] = b64url_encode(zero_key)
    zero_manifest_document["keys"][0]["kid"] = sha256_hex(zero_key)
    zero_manifest_bytes = canonical_json(zero_manifest_document)
    zero_manifest = KeyManifest.parse(zero_manifest_bytes, sha256_hex(zero_manifest_bytes))
    zero_profile = replace(command.profile, key_manifest_sha256=zero_manifest.digest)
    zero_carrier = replace(command.carrier, key_manifest_sha256=zero_manifest.digest)
    zero_context = copy.deepcopy(command.ncp_context)
    zero_context["kid"] = zero_manifest.keys[0].kid
    zero_context["key_manifest_sha256"] = zero_manifest.digest
    add_case(
        cases,
        "reject-small-order-public-key",
        "manifest contains the identity compressed point",
        request_bytes(
            command,
            envelope=resigned(command, zero_context),
            manifest_bytes=zero_manifest_bytes,
            profile=zero_profile,
            carrier=zero_carrier,
        ),
    )

    add_case(
        cases,
        "reject-carrier-principal-equals-signer",
        "transport carrier principal launders signer identity",
        request_bytes(
            command,
            carrier=replace(command.carrier, principal_id=command.ncp_context["issuer"]),
        ),
    )
    add_case(
        cases,
        "reject-carrier-entity-equals-signer",
        "transport carrier entity launders signer entity",
        request_bytes(
            command,
            carrier=replace(command.carrier, entity_id="pid-controller-1"),
        ),
    )

    wrong_route = copy.deepcopy(command.ncp_context)
    wrong_route["route"] = "ncp/other"
    add_case(
        cases,
        "reject-protected-route-mismatch",
        "signed route differs from endpoint",
        request_bytes(command, envelope=resigned(command, wrong_route)),
    )

    stale = copy.deepcopy(command.ncp_context)
    stale["expires_at_utc_ms"] = NOW - 1
    add_case(
        cases,
        "reject-expired-envelope",
        "signed interval is stale",
        request_bytes(command, envelope=resigned(command, stale)),
    )

    payload_value = json.loads(command.payload)
    payload_value["session_id"] = "different-session"
    mismatched_payload = canonical_json(payload_value)
    payload_context = copy.deepcopy(command.ncp_context)
    payload_context["payload_sha256"] = sha256_hex(mismatched_payload)
    add_case(
        cases,
        "reject-payload-session-mismatch",
        "payload session differs from protected context",
        request_bytes(
            command,
            envelope=resigned(command, payload_context, mismatched_payload),
        ),
    )

    stream_context = copy.deepcopy(command.ncp_context)
    stream_context["payload_stream"]["sequence"] += 1
    add_case(
        cases,
        "reject-payload-stream-mismatch",
        "protected stream sequence differs from signed payload",
        request_bytes(command, envelope=resigned(command, stream_context)),
    )

    add_case(
        cases,
        "reject-a-direct-profile",
        "forwarding verifier cannot run on an A-direct endpoint",
        request_bytes(command, profile=replace(command.profile, mode="a-direct")),
    )

    next_signer = SigningKey.generate()
    overlap_document = copy.deepcopy(manifest_document)
    next_entry = copy.deepcopy(overlap_document["keys"][0])
    next_public = next_signer.verify_key.encode()
    next_entry["kid"] = sha256_hex(next_public)
    next_entry["public_key"] = b64url_encode(next_public)
    next_entry["key_epoch"] = 2
    overlap_document["generation"] = 2
    overlap_document["keys"].append(next_entry)
    overlap_bytes = canonical_json(overlap_document)
    overlap = KeyManifest.parse(overlap_bytes, sha256_hex(overlap_bytes))
    overlap_profile = replace(
        command.profile,
        key_manifest_sha256=overlap.digest,
        key_manifest_generation=2,
    )
    overlap_carrier = replace(
        command.carrier,
        key_manifest_sha256=overlap.digest,
        key_manifest_generation=2,
    )
    old_context = copy.deepcopy(command.ncp_context)
    old_context["key_manifest_generation"] = 2
    old_context["key_manifest_sha256"] = overlap.digest
    add_case(
        cases,
        "accept-overlap-old-key",
        "old key remains exact during manifest overlap",
        request_bytes(
            command,
            envelope=resigned(command, old_context),
            manifest_bytes=overlap_bytes,
            profile=overlap_profile,
            carrier=overlap_carrier,
        ),
    )
    next_context = copy.deepcopy(old_context)
    next_context["kid"] = next_entry["kid"]
    next_context["key_epoch"] = 2
    add_case(
        cases,
        "accept-overlap-next-key",
        "next key is accepted only with its exact epoch",
        request_bytes(
            command,
            envelope=build_envelope(
                next_signer,
                ncp_context=next_context,
                payload=command.payload,
            ),
            manifest_bytes=overlap_bytes,
            profile=overlap_profile,
            carrier=overlap_carrier,
        ),
    )

    removed_document = copy.deepcopy(overlap_document)
    removed_document["generation"] = 3
    removed_document["keys"] = [next_entry]
    removed_bytes = canonical_json(removed_document)
    removed = KeyManifest.parse(removed_bytes, sha256_hex(removed_bytes))
    removed_profile = replace(
        overlap_profile,
        key_manifest_sha256=removed.digest,
        key_manifest_generation=3,
    )
    removed_carrier = replace(
        overlap_carrier,
        key_manifest_sha256=removed.digest,
        key_manifest_generation=3,
    )
    removed_context = copy.deepcopy(old_context)
    removed_context["key_manifest_generation"] = 3
    removed_context["key_manifest_sha256"] = removed.digest
    add_case(
        cases,
        "reject-removed-old-key",
        "removed key has no fallback after overlap",
        request_bytes(
            command,
            envelope=resigned(command, removed_context),
            manifest_bytes=removed_bytes,
            profile=removed_profile,
            carrier=removed_carrier,
        ),
    )

    return {
        "cases": cases,
        "private_material_retained": False,
        "schema": CORPUS_SCHEMA,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    document = generate()
    options.output.write_bytes(canonical_json(document) + b"\n")
    print(f"wrote {len(document['cases'])} public differential cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
