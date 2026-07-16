"""Hostile syntax, cryptographic, routing, and payload-binding tests."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from nacl.signing import SigningKey

from prototype.forwarding import (
    CarrierContext,
    KeyManifest,
    build_envelope,
    verify_and_commit,
)
from prototype.replay import ReplayStore
from prototype.strict import (
    ErrorCode,
    PrototypeError,
    b64url_decode,
    b64url_encode,
    sha256_hex,
)
from tests.common import (
    NOW,
    Material,
    canonical_json,
    initialize_store,
    manifest_for,
    material,
    resigned,
)


def verify(value: Material, store: ReplayStore, envelope: bytes | None = None):
    return verify_and_commit(
        value.envelope if envelope is None else envelope,
        manifest=value.manifest,
        profile=value.profile,
        carrier=value.carrier,
        replay_store=store,
        now_utc_ms=NOW,
    )


def outer(envelope: bytes) -> dict[str, str]:
    return json.loads(envelope)


def protected(envelope: bytes) -> dict[str, object]:
    return json.loads(b64url_decode(outer(envelope)["protected"], maximum=16_384))


def custom_header(
    value: Material, header: dict[str, object], payload: bytes | None = None
) -> bytes:
    payload = value.payload if payload is None else payload
    protected_b64 = b64url_encode(canonical_json(header))
    payload_b64 = b64url_encode(payload)
    signature = value.signer.sign(f"{protected_b64}.{payload_b64}".encode()).signature
    return canonical_json(
        {
            "payload": payload_b64,
            "protected": protected_b64,
            "signature": b64url_encode(signature),
        }
    )


class ForwardingTests(unittest.TestCase):
    def test_accepts_command_and_operation_profiles_without_granting_authority(self) -> None:
        for message_class in ("command_frame", "step_request"):
            with self.subTest(message_class=message_class), tempfile.TemporaryDirectory() as tmp:
                value = material(message_class)
                path, pinned = initialize_store(Path(tmp), value.owner)
                with ReplayStore.open(path, pinned) as store:
                    accepted = verify(value, store)
                self.assertEqual(accepted.payload, value.payload)
                self.assertEqual(accepted.context.signer_principal_id, "controller-principal-1")
                self.assertEqual(accepted.context.carrier_principal_id, "ingress-forwarder-1")
                self.assertEqual(accepted.context.carrier_entity_id, "ingress-process-1")
                self.assertEqual(accepted.context.carrier_transport_role, "forwarder")
                self.assertEqual(accepted.context.carrier_profile, "b-over-a-forwarding")
                self.assertEqual(accepted.context.stable_core_sha256, "1" * 64)
                self.assertEqual(accepted.context.security_state_sha256, "2" * 64)
                self.assertNotEqual(
                    accepted.context.signer_principal_id,
                    accepted.context.carrier_principal_id,
                )
                self.assertFalse(hasattr(accepted.context, "lease"))
                self.assertFalse(hasattr(accepted.context, "authority"))

    def test_duplicate_lower_and_independent_forwarding_scopes_reject_or_accept(self) -> None:
        value = material(forwarding_sequence=2)
        with tempfile.TemporaryDirectory() as tmp:
            path, pinned = initialize_store(Path(tmp), value.owner)
            with ReplayStore.open(path, pinned) as store:
                verify(value, store)
                with self.assertRaisesRegex(PrototypeError, "equal or lower"):
                    verify(value, store)
                lower_context = copy.deepcopy(value.ncp_context)
                lower_context["forwarding_sequence"] = 1
                with self.assertRaisesRegex(PrototypeError, "equal or lower"):
                    verify(value, store, resigned(value, lower_context))
                changed_payload = value.payload + b" "
                changed_context = copy.deepcopy(value.ncp_context)
                changed_context["payload_sha256"] = sha256_hex(changed_payload)
                with self.assertRaisesRegex(PrototypeError, "equal or lower"):
                    verify(
                        value,
                        store,
                        resigned(value, changed_context, changed_payload),
                    )
                other_context = copy.deepcopy(value.ncp_context)
                other_context["forwarding_epoch"] = "40000000-0000-4000-8000-000000000004"
                accepted = verify(value, store, resigned(value, other_context))
                self.assertEqual(accepted.context.forwarding_sequence, 2)

    def test_flattened_form_base64url_utf8_and_integer_ambiguity_reject(self) -> None:
        value = material()
        hostile: list[tuple[bytes, ErrorCode]] = []
        parsed_outer = outer(value.envelope)
        hostile.append((b"a.b.c", ErrorCode.JSON))
        hostile.append(
            (
                canonical_json({**parsed_outer, "header": {}}),
                ErrorCode.PROFILE,
            )
        )
        padded = dict(parsed_outer)
        padded["protected"] += "="
        hostile.append((canonical_json(padded), ErrorCode.ENCODING))
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
        ).encode()
        hostile.append((duplicate_outer, ErrorCode.JSON))
        hostile.append(
            (
                b'{"payload":"x","protected":"\\ud800","signature":"x"}',
                ErrorCode.JSON,
            )
        )
        hostile.append((b"\xff", ErrorCode.ENCODING))
        unsafe = copy.deepcopy(value.ncp_context)
        unsafe["forwarding_sequence"] = 9_007_199_254_740_992
        hostile.append((resigned(value, unsafe), ErrorCode.BOUNDS))

        for envelope, code in hostile:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                path, pinned = initialize_store(Path(tmp), value.owner)
                with ReplayStore.open(path, pinned) as store:
                    with self.assertRaises(PrototypeError) as caught:
                        verify(value, store, envelope)
                self.assertEqual(caught.exception.code, code)

    def test_algorithm_remote_key_changed_bytes_and_noncanonical_signature_reject(self) -> None:
        value = material()
        hostile: list[bytes] = []

        wrong_algorithm = protected(value.envelope)
        wrong_algorithm["alg"] = "EdDSA"
        hostile.append(custom_header(value, wrong_algorithm))

        remote_key = protected(value.envelope)
        remote_key["jwk"] = {"kty": "OKP"}
        hostile.append(custom_header(value, remote_key))

        changed_payload = bytearray(value.payload)
        changed_payload[-2] ^= 1
        parsed = outer(value.envelope)
        parsed["payload"] = b64url_encode(bytes(changed_payload))
        hostile.append(canonical_json(parsed))

        parsed = outer(value.envelope)
        signature = bytearray(b64url_decode(parsed["signature"], maximum=64))
        order = 2**252 + 27742317777372353535851937790883648493
        scalar = int.from_bytes(signature[32:], "little") + order
        signature[32:] = scalar.to_bytes(32, "little")
        parsed["signature"] = b64url_encode(signature)
        hostile.append(canonical_json(parsed))

        for envelope in hostile:
            with tempfile.TemporaryDirectory() as tmp:
                path, pinned = initialize_store(Path(tmp), value.owner)
                with ReplayStore.open(path, pinned) as store:
                    with self.assertRaises(PrototypeError):
                        verify(value, store, envelope)

    def test_manifest_unknown_key_wildcard_and_small_order_key_reject(self) -> None:
        value = material()
        manifest_value = json.loads(value.manifest_bytes)
        cases: list[bytes] = []

        unknown = copy.deepcopy(manifest_value)
        unknown["keys"][0]["extra"] = True
        cases.append(canonical_json(unknown))

        wildcard = copy.deepcopy(manifest_value)
        wildcard["keys"][0]["grants"][0]["route"] = "ncp/*"
        cases.append(canonical_json(wildcard))

        small_order = copy.deepcopy(manifest_value)
        small_order["keys"][0]["public_key"] = b64url_encode(bytes(32))
        small_order["keys"][0]["kid"] = sha256_hex(bytes(32))
        cases.append(canonical_json(small_order))

        for index, exact in enumerate(cases):
            with self.subTest(exact=sha256_hex(exact)):
                if index == len(cases) - 1:
                    manifest = KeyManifest.parse(exact, sha256_hex(exact))
                    profile = replace(value.profile, key_manifest_sha256=manifest.digest)
                    carrier = replace(value.carrier, key_manifest_sha256=manifest.digest)
                    context = copy.deepcopy(value.ncp_context)
                    context["kid"] = manifest.keys[0].kid
                    context["key_manifest_sha256"] = manifest.digest
                    envelope = resigned(value, context)
                    with tempfile.TemporaryDirectory() as tmp:
                        path, pinned = initialize_store(Path(tmp), value.owner)
                        with ReplayStore.open(path, pinned) as store:
                            with self.assertRaisesRegex(PrototypeError, "Ed25519"):
                                verify_and_commit(
                                    envelope,
                                    manifest=manifest,
                                    profile=profile,
                                    carrier=carrier,
                                    replay_store=store,
                                    now_utc_ms=NOW,
                                )
                else:
                    with self.assertRaises(PrototypeError):
                        KeyManifest.parse(exact, sha256_hex(exact))
        oversized = b"x" * 65_537
        with self.assertRaisesRegex(PrototypeError, "byte length"):
            KeyManifest.parse(oversized, sha256_hex(oversized))

    def test_carrier_signer_routing_clock_and_payload_congruence_reject(self) -> None:
        value = material()
        hostile: list[tuple[CarrierContext, bytes]] = []

        wrong_carrier = replace(value.carrier, route="ncp/other")
        hostile.append((wrong_carrier, value.envelope))

        signer_carrier = replace(
            value.carrier,
            principal_id="controller-principal-1",
        )
        hostile.append((signer_carrier, value.envelope))
        signer_entity_carrier = replace(
            value.carrier,
            entity_id="pid-controller-1",
        )
        hostile.append((signer_entity_carrier, value.envelope))

        stale = copy.deepcopy(value.ncp_context)
        stale["expires_at_utc_ms"] = NOW - 1
        hostile.append((value.carrier, resigned(value, stale)))

        wrong_route = copy.deepcopy(value.ncp_context)
        wrong_route["route"] = "ncp/other"
        hostile.append((value.carrier, resigned(value, wrong_route)))

        payload_value = json.loads(value.payload)
        payload_value["session_id"] = "different-session"
        payload = json.dumps(payload_value, separators=(",", ":")).encode()
        payload_mismatch = copy.deepcopy(value.ncp_context)
        payload_mismatch["payload_sha256"] = sha256_hex(payload)
        hostile.append((value.carrier, resigned(value, payload_mismatch, payload)))

        for carrier, envelope in hostile:
            with tempfile.TemporaryDirectory() as tmp:
                path, pinned = initialize_store(Path(tmp), value.owner)
                with ReplayStore.open(path, pinned) as store:
                    with self.assertRaises(PrototypeError):
                        verify_and_commit(
                            envelope,
                            manifest=value.manifest,
                            profile=value.profile,
                            carrier=carrier,
                            replay_store=store,
                            now_utc_ms=NOW,
                        )

        direct_profile = replace(value.profile, mode="a-direct")
        with tempfile.TemporaryDirectory() as tmp:
            path, pinned = initialize_store(Path(tmp), value.owner)
            with ReplayStore.open(path, pinned) as store:
                with self.assertRaisesRegex(PrototypeError, "forwarding-only"):
                    verify_and_commit(
                        value.envelope,
                        manifest=value.manifest,
                        profile=direct_profile,
                        carrier=value.carrier,
                        replay_store=store,
                        now_utc_ms=NOW,
                    )

    def test_wrong_signer_key_and_manifest_digest_reject_without_fallback(self) -> None:
        value = material()
        other_key = SigningKey.generate()
        other_bytes, other_manifest = manifest_for(other_key, "command_frame")
        self.assertNotEqual(other_bytes, value.manifest_bytes)
        with tempfile.TemporaryDirectory() as tmp:
            path, pinned = initialize_store(Path(tmp), value.owner)
            with ReplayStore.open(path, pinned) as store:
                with self.assertRaises(PrototypeError):
                    verify_and_commit(
                        value.envelope,
                        manifest=other_manifest,
                        profile=value.profile,
                        carrier=value.carrier,
                        replay_store=store,
                        now_utc_ms=NOW,
                    )

        with self.assertRaisesRegex(PrototypeError, "digest"):
            KeyManifest.parse(value.manifest_bytes, "0" * 64)

    def test_key_rotation_overlap_is_exact_and_removed_key_has_no_fallback(self) -> None:
        value = material()
        next_key = SigningKey.generate()
        document = json.loads(value.manifest_bytes)
        next_entry = copy.deepcopy(document["keys"][0])
        next_public = next_key.verify_key.encode()
        next_entry["kid"] = sha256_hex(next_public)
        next_entry["public_key"] = b64url_encode(next_public)
        next_entry["key_epoch"] = 2
        document["generation"] = 2
        document["keys"].append(next_entry)
        overlap_bytes = canonical_json(document)
        overlap = KeyManifest.parse(overlap_bytes, sha256_hex(overlap_bytes))
        profile = replace(
            value.profile,
            key_manifest_sha256=overlap.digest,
            key_manifest_generation=2,
        )
        carrier = replace(
            value.carrier,
            key_manifest_sha256=overlap.digest,
            key_manifest_generation=2,
        )
        old_context = copy.deepcopy(value.ncp_context)
        old_context["key_manifest_generation"] = 2
        old_context["key_manifest_sha256"] = overlap.digest
        new_context = copy.deepcopy(old_context)
        new_context["kid"] = next_entry["kid"]
        new_context["key_epoch"] = 2

        with tempfile.TemporaryDirectory() as tmp:
            path, pinned = initialize_store(Path(tmp), value.owner)
            with ReplayStore.open(path, pinned) as store:
                verify_and_commit(
                    build_envelope(
                        value.signer,
                        ncp_context=old_context,
                        payload=value.payload,
                    ),
                    manifest=overlap,
                    profile=profile,
                    carrier=carrier,
                    replay_store=store,
                    now_utc_ms=NOW,
                )
                verify_and_commit(
                    build_envelope(
                        next_key,
                        ncp_context=new_context,
                        payload=value.payload,
                    ),
                    manifest=overlap,
                    profile=profile,
                    carrier=carrier,
                    replay_store=store,
                    now_utc_ms=NOW,
                )

        document["generation"] = 3
        document["keys"] = [next_entry]
        removed_bytes = canonical_json(document)
        removed = KeyManifest.parse(removed_bytes, sha256_hex(removed_bytes))
        removed_profile = replace(
            profile,
            key_manifest_sha256=removed.digest,
            key_manifest_generation=3,
        )
        removed_carrier = replace(
            carrier,
            key_manifest_sha256=removed.digest,
            key_manifest_generation=3,
        )
        removed_context = copy.deepcopy(old_context)
        removed_context["key_manifest_generation"] = 3
        removed_context["key_manifest_sha256"] = removed.digest
        with tempfile.TemporaryDirectory() as tmp:
            path, pinned = initialize_store(Path(tmp), value.owner)
            with ReplayStore.open(path, pinned) as store:
                with self.assertRaisesRegex(PrototypeError, "absent"):
                    verify_and_commit(
                        build_envelope(
                            value.signer,
                            ncp_context=removed_context,
                            payload=value.payload,
                        ),
                        manifest=removed,
                        profile=removed_profile,
                        carrier=removed_carrier,
                        replay_store=store,
                        now_utc_ms=NOW,
                    )


if __name__ == "__main__":
    unittest.main()
