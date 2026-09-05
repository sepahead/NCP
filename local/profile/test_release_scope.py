"""Release labels cannot replace source, profile, or receipt evidence."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "scope_gate", ROOT / "scripts/check_local_scope.py"
)
scope_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope_gate)


class ReleaseScopeTests(unittest.TestCase):
    def setUp(self):
        self.scope = json.loads((ROOT / "local/release.v1.json").read_text())

    def test_registered_unreleased_scope_has_no_completion_authority(self):
        checked = scope_gate.check_scope(self.scope)
        self.assertEqual(checked["status"], "unreleased")
        self.assertFalse(checked["scientific_validation"])

    def test_individual_failed_requirements_cannot_be_waived_by_labels(self):
        mutations = [
            lambda s: s.update(status="qualified"),
            lambda s: s.update(status="published"),
            lambda s: s.update(status="passed"),
            lambda s: s.update(scientific_validation=True),
            lambda s: s.update(descriptor_raw_sha256="0" * 64),
            lambda s: s.update(descriptor_typed_digest="0" * 64),
            lambda s: s.update(bootstrap_requirements=[]),
            lambda s: s["historical_scope"].update(
                local_release_can_promote_historical_gates=True
            ),
            lambda s: s["application_roles"][0].update(role="body"),
            lambda s: s["packages"][0].update(manifest="../Cargo.toml"),
            lambda s: s["packages"][0].update(name="ncp-core"),
            lambda s: s.update(
                bootstrap_receipt={"path": "README.md", "sha256": "0" * 64}
            ),
        ]
        for index, change in enumerate(mutations):
            with self.subTest(index=index):
                altered = copy.deepcopy(self.scope)
                change(altered)
                with self.assertRaises(ValueError):
                    scope_gate.check_scope(altered)
        scope_gate.check_scope(self.scope)

    def test_scope_digest_binds_requirements_but_not_later_receipt_references(self):
        before = scope_gate.scope_digest(self.scope)
        changed = copy.deepcopy(self.scope)
        changed["status"] = "published"
        changed["publication_receipt"] = {"path": "unexecuted", "sha256": "0" * 64}
        self.assertEqual(before, scope_gate.scope_digest(changed))
        with self.assertRaises(ValueError):
            scope_gate.check_scope(changed)
        changed = copy.deepcopy(self.scope)
        changed["operational_requirements"][0] += " changed"
        self.assertNotEqual(before, scope_gate.scope_digest(changed))

    def test_complete_synthetic_receipt_structure_is_checked_without_execution_claim(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [
                self.scope["descriptor"],
                self.scope["historical_scope"]["scope"],
                self.scope["historical_scope"]["gates"],
                *(row["manifest"] for row in self.scope["packages"]),
            ]
            for name in paths:
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, root / name)

            def evidence(name, data):
                payload = json.dumps(data).encode()
                (root / name).write_bytes(payload)
                return {"path": name, "sha256": hashlib.sha256(payload).hexdigest()}

            # These fixtures test metadata checking only. They are never placed
            # in the repository's actual evidence ledger or used to run code.
            manifest = evidence("synthetic-manifest.json", {"synthetic_fixture": True})
            log = evidence("synthetic-log.json", {"executed": False, "fixture": True})
            changed = copy.deepcopy(self.scope)
            for stage, key in (
                ("bootstrap", "bootstrap_requirements"),
                ("operational", "operational_requirements"),
                ("publication", "post_publication_requirements"),
            ):
                receipt = {
                    "schema": "ncp.local.release-receipt.v1",
                    "stage": stage,
                    "profile_digest": changed["descriptor_typed_digest"],
                    "scope_digest": scope_gate.scope_digest(changed),
                    "status": "passed",
                    "source_commits": {"NCP": "1" * 40},
                    "artifact_manifest": manifest,
                    "checks": [
                        {
                            "requirement": requirement,
                            "result": "passed",
                            "evidence": log,
                        }
                        for requirement in changed[key]
                    ],
                    "scientific_validation": False,
                }
                changed[stage + "_receipt"] = evidence(stage + ".json", receipt)
            changed["status"] = "published"
            checked = scope_gate.check_scope(changed, root)
            self.assertEqual(
                checked["validation_scope"],
                "structure, identity, coverage, and referenced file hashes",
            )
            self.assertFalse(checked["scientific_validation"])
            # A complete-looking receipt cannot replace a missing required gate.
            receipt["checks"].pop()
            changed["publication_receipt"] = evidence("publication.json", receipt)
            with self.assertRaises(ValueError):
                scope_gate.check_scope(changed, root)


if __name__ == "__main__":
    unittest.main()
