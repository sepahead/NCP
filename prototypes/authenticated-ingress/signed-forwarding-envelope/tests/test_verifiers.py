"""Hostile self-tests for dependency/source and live-result verifiers."""

from __future__ import annotations

import copy
import json
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import verify_profile  # noqa: E402
import verify_result  # noqa: E402


class ProfileVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project = tomllib.loads((ROOT / "pyproject.toml").read_text())
        self.lock = tomllib.loads((ROOT / "uv.lock").read_text())
        self.forwarding = (ROOT / "prototype" / "forwarding.py").read_text()
        self.replay = (ROOT / "prototype" / "replay.py").read_text()

    def test_accepts_exact_reviewed_boundary(self) -> None:
        verify_profile.verify_pyproject(self.project)
        verify_profile.verify_lock(self.lock)
        verify_profile.verify_source(self.forwarding, self.replay)

    def test_rejects_dependency_drift(self) -> None:
        mutant = copy.deepcopy(self.project)
        mutant["project"]["dependencies"] = ["PyNaCl>=1.6"]
        with self.assertRaises(verify_profile.VerificationError):
            verify_profile.verify_pyproject(mutant)

    def test_rejects_normal_synchronous_mode(self) -> None:
        with self.assertRaises(verify_profile.VerificationError):
            verify_profile.verify_source(
                self.forwarding,
                self.replay + "\nsynchronous=NORMAL\n",
            )

    def test_rejects_unconditional_replacement(self) -> None:
        with self.assertRaises(verify_profile.VerificationError):
            verify_profile.verify_source(
                self.forwarding,
                self.replay + "\nINSERT OR REPLACE\n",
            )


class ResultVerifierTests(unittest.TestCase):
    def result(self) -> dict[str, object]:
        return {
            "schema": verify_result.SCHEMA,
            "scope": "quarantined-local-feasibility",
            "profiles": ["command_frame", "step_request"],
            "crypto": {
                "algorithm": "Ed25519",
                "library": "PyNaCl",
                "pynacl_version": "1.6.2",
                "signing_input_uses_received_encoded_strings": True,
            },
            "replay": {
                "sqlite_version": "3.53.2",
                "journal_mode": "wal",
                "synchronous": "FULL",
                "begin_mode": "IMMEDIATE",
                "conditional_upsert": True,
                "commit_before_handoff": True,
                "delivery_semantics": "at-most-once-with-explicit-crash-loss-window",
                "recovery_epoch_signed": True,
                "filesystem_rollback_detected": False,
                "scope_capacity": 128,
            },
            "resources": {
                "accepted_messages": 2,
                "elapsed_microseconds_local": 1,
                "largest_envelope_bytes": 4_096,
                "largest_manifest_bytes": 1_024,
                "largest_payload_bytes": 2_048,
                "largest_protected_bytes": 1_024,
                "largest_replay_database_bytes": 65_536,
                "envelope_limit_bytes": 1_500_000,
                "manifest_limit_bytes": 65_536,
                "payload_limit_bytes": 1_048_576,
                "protected_limit_bytes": 16_384,
                "replay_database_limit_bytes": 8_388_608,
            },
            "claim_boundary": {
                "ncp_authority_granted": False,
                "plant_action_granted": False,
                "production_security_proved": False,
                "filesystem_rollback_protection_proved": False,
                "independent_parser_gate_satisfied": True,
                "b04_complete": False,
                "release_gate_satisfied": False,
            },
        }

    def test_accepts_reviewed_result_and_exactly_one_line(self) -> None:
        result = self.result()
        verify_result.verify(result)
        self.assertEqual(
            verify_result.extract(f"noise\n{verify_result.PREFIX}{json.dumps(result)}\n"),
            result,
        )
        duplicate = json.dumps(result)[:-1] + ',"schema":"duplicate"}'
        with self.assertRaises(verify_result.ResultError):
            verify_result.extract(f"{verify_result.PREFIX}{duplicate}\n")

    def test_rejects_release_promotion(self) -> None:
        result = self.result()
        result["claim_boundary"]["release_gate_satisfied"] = True
        with self.assertRaises(verify_result.ResultError):
            verify_result.verify(result)
        result = self.result()
        del result["claim_boundary"]["b04_complete"]
        with self.assertRaises(verify_result.ResultError):
            verify_result.verify(result)
        result = self.result()
        result["unreviewed"] = False
        with self.assertRaises(verify_result.ResultError):
            verify_result.verify(result)

    def test_rejects_rollback_overclaim(self) -> None:
        result = self.result()
        result["replay"]["filesystem_rollback_detected"] = True
        with self.assertRaises(verify_result.ResultError):
            verify_result.verify(result)

    def test_rejects_resource_overrun(self) -> None:
        result = self.result()
        result["resources"]["largest_payload_bytes"] = 1_048_577
        with self.assertRaises(verify_result.ResultError):
            verify_result.verify(result)


if __name__ == "__main__":
    unittest.main()
