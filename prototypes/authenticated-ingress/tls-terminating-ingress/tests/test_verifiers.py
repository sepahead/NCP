#!/usr/bin/env python3
"""Hostile self-tests for the TLS-ingress result and feature verifiers."""

from __future__ import annotations

import copy
import json
import sys
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import verify_features  # noqa: E402
import verify_result  # noqa: E402


class FeatureVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = tomllib.loads(
            (ROOT / "Cargo.toml").read_text(encoding="utf-8")
        )
        self.source = (ROOT / "src" / "lib.rs").read_text(encoding="utf-8")

    def test_accepts_exact_manifest_and_source(self) -> None:
        verify_features.verify_manifest(self.manifest)
        verify_features.verify_source(self.source)

    def test_rejects_tls12_feature_enablement(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["dependencies"]["rustls"]["features"].append("tls12")
        with self.assertRaises(verify_features.VerificationError):
            verify_features.verify_manifest(mutated)

    def test_rejects_optional_client_auth(self) -> None:
        with self.assertRaises(verify_features.VerificationError):
            verify_features.verify_source(self.source + "\nallow_unauthenticated\n")

    def test_rejects_context_detachment_surface(self) -> None:
        with self.assertRaises(verify_features.VerificationError):
            verify_features.verify_source(self.source + "\npub fn into_parts\n")


class ResultVerifierTests(unittest.TestCase):
    def result(self) -> dict[str, object]:
        return {
            "schema": verify_result.SCHEMA,
            "scope": "quarantined-local-feasibility",
            "tls": {
                "version": "1.3",
                "provider": "ring",
                "client_certificate_required": True,
                "alpn": "ncp-prototype-a/1",
                "tickets_sent": 0,
                "resumption_accepted": False,
                "zero_rtt_accepted": False,
            },
            "binding": {
                "exact_leaf_der_sha256": True,
                "manifest_default_deny": True,
                "payload_identity_exact_match": True,
                "manifest_generation": 1,
                "same_immutable_payload": True,
                "context_serialized": False,
            },
            "replay_probe": {
                "ingress_admitted_identical_messages": 2,
                "duplicate_observations": [False, True],
                "durable": False,
                "affects_admission": False,
            },
            "resources": {
                "manifest_bytes": 512,
                "manifest_limit_bytes": 65_536,
                "payload_bytes": 1_024,
                "frame_limit_bytes": 1_048_576,
                "connections": 2,
                "elapsed_microseconds_local": 1,
            },
            "claim_boundary": {
                "production_security_proved": False,
                "live_rotation_revocation_gate_satisfied": False,
                "authorization_granted": False,
                "plant_authority_granted": False,
                "release_gate_satisfied": False,
            },
        }

    def test_accepts_reviewed_result(self) -> None:
        result = self.result()
        verify_result.verify(result)
        extracted = verify_result.extract(
            f"noise\n{verify_result.PREFIX}{json.dumps(result)}\n"
        )
        self.assertEqual(extracted, result)

    def test_rejects_optimistic_gate_promotion(self) -> None:
        result = self.result()
        result["claim_boundary"]["release_gate_satisfied"] = True
        with self.assertRaises(verify_result.ResultVerificationError):
            verify_result.verify(result)

    def test_rejects_unbounded_payload_observation(self) -> None:
        result = self.result()
        result["resources"]["payload_bytes"] = 1_048_577
        with self.assertRaises(verify_result.ResultVerificationError):
            verify_result.verify(result)

    def test_rejects_replay_mock_becoming_admission(self) -> None:
        result = self.result()
        result["replay_probe"]["affects_admission"] = True
        with self.assertRaises(verify_result.ResultVerificationError):
            verify_result.verify(result)


if __name__ == "__main__":
    unittest.main()
