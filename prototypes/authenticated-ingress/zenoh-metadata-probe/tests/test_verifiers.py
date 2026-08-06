"""Hostile tests for the quarantined probe's evidence verifiers."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROBE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROBE_ROOT))

from verify_result import EXPECTED, ResultVerificationError, verify  # noqa: E402
from verify_source_matrix import (  # noqa: E402
    VerificationError,
    verify_feature_boundary,
    verify_files,
    verify_manifest_patch,
)


class FeatureBoundaryTests(unittest.TestCase):
    @staticmethod
    def metadata(features: list[str]) -> dict[str, object]:
        return {
            "packages": [
                {
                    "id": "zenoh-transport-id",
                    "name": "zenoh-transport",
                    "version": "1.9.0",
                }
            ],
            "resolve": {"nodes": [{"id": "zenoh-transport-id", "features": features}]},
        }

    def test_reviewed_transport_features_are_accepted(self) -> None:
        verify_feature_boundary(self.metadata(["transport_tcp", "unstable"]))

    def test_compression_feature_is_rejected(self) -> None:
        with self.assertRaisesRegex(VerificationError, "compression"):
            verify_feature_boundary(
                self.metadata(["transport_compression", "transport_tcp"])
            )


class SourceFileBoundaryTests(unittest.TestCase):
    def test_parent_path_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            crate_root = parent / "crate"
            crate_root.mkdir()
            outside = parent / "outside.rs"
            outside.write_text("reviewed fragment", encoding="utf-8")
            item = {
                "path": "../outside.rs",
                "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                "required_fragments": ["reviewed fragment"],
            }
            with self.assertRaisesRegex(VerificationError, "escapes"):
                verify_files(crate_root, [item])

    def test_wrong_hash_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            crate_root = Path(directory)
            source = crate_root / "source.rs"
            source.write_text("reviewed fragment", encoding="utf-8")
            item = {
                "path": "source.rs",
                "sha256": "0" * 64,
                "required_fragments": ["reviewed fragment"],
            }
            with self.assertRaisesRegex(VerificationError, "hash differs"):
                verify_files(crate_root, [item])


class BackportIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backport = {
            "repository": "https://github.com/sepahead/zenoh-transport-lz4-backport",
            "revision": "9045545b72a77602a87f40203cb614b48157b4bc",
        }

    def test_exact_manifest_patch_is_accepted(self) -> None:
        manifest = {
            "patch": {
                "crates-io": {
                    "zenoh-transport": {
                        "git": self.backport["repository"],
                        "rev": self.backport["revision"],
                    }
                }
            }
        }
        verify_manifest_patch(manifest, self.backport)

    def test_wrong_manifest_revision_is_rejected(self) -> None:
        manifest = {
            "patch": {
                "crates-io": {
                    "zenoh-transport": {
                        "git": self.backport["repository"],
                        "rev": "0" * 40,
                    }
                }
            }
        }
        with self.assertRaisesRegex(VerificationError, "identity"):
            verify_manifest_patch(manifest, self.backport)


class ResultBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.expected = json.loads(EXPECTED.read_text(encoding="utf-8"))

    def test_exact_result_is_accepted(self) -> None:
        verify(self.expected, self.expected)

    def test_external_gate_promotion_is_rejected(self) -> None:
        promoted = copy.deepcopy(self.expected)
        promoted["claim_boundary"]["external_gate_satisfied"] = True
        with self.assertRaises(ResultVerificationError):
            verify(promoted, self.expected)

    def test_missing_observation_is_rejected(self) -> None:
        incomplete = copy.deepcopy(self.expected)
        del incomplete["observations"]["liveliness_delete_source_was_none"]
        with self.assertRaises(ResultVerificationError):
            verify(incomplete, self.expected)


if __name__ == "__main__":
    unittest.main()
