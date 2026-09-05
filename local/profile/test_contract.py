"""Independent descriptor shape checks and native Rust/Python contract controls.

Run with the explicit Rust probe path. Missing test dependencies or the probe
fail this gate; no required check is converted to an optional skip.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import unittest

from jsonschema import Draft202012Validator, ValidationError, validators

from ncp_local import (
    LocalBinding,
    LocalError,
    LocalOwner,
    decode,
    encode,
    digest_without,
    local_digest,
    make_request,
    profile_descriptor_bytes,
    profile_digest,
    read_local_frame,
    write_local_frame,
    verify_integrity,
)

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "local_data_controls", ROOT / "local/python/tests/test_data.py"
)
data_controls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(data_controls)


class EmptyBackend:
    def validate(self, operation, body):
        if operation != "prepare" or body != {}:
            raise LocalError("invalid_input")

    def execute(self, operation, body):
        return {}

    def retire(self):
        pass


def lexical_integer(_validator, required, instance, _schema):
    if required and type(instance) is not int:
        yield ValidationError("the wire field requires a lexical integer")


def utf8_bytes(_validator, maximum, instance, _schema):
    if type(instance) is str:
        try:
            if len(instance.encode("utf-8")) > maximum:
                yield ValidationError("the decoded UTF-8 byte bound is exceeded")
        except UnicodeError:
            yield ValidationError("invalid Unicode scalar value")


ContractValidator = validators.extend(
    Draft202012Validator,
    {"x-lexical-integer": lexical_integer, "x-max-utf8-bytes": utf8_bytes},
)


class DescriptorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.descriptor = decode(profile_descriptor_bytes())
        cls.definitions = cls.descriptor["data_schema"]["$defs"]
        probe = os.environ.get("NCP_LOCAL_CONTRACT_PROBE")
        if not probe:
            raise RuntimeError("NCP_LOCAL_CONTRACT_PROBE is required for this gate")
        cls.process = subprocess.Popen(
            [probe],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

    @classmethod
    def tearDownClass(cls):
        cls.process.stdin.close()
        try:
            cls.process.wait(timeout=5)
            if cls.process.returncode != 0:
                raise AssertionError(cls.process.stderr.read().decode())
        finally:
            if cls.process.poll() is None:
                cls.process.kill()
                cls.process.wait(timeout=5)
            for stream in (cls.process.stdin, cls.process.stdout, cls.process.stderr):
                stream.close()

    def native(self, value):
        deadline = time.monotonic() + 5
        write_local_frame(self.process.stdin, encode(value), deadline=deadline)
        response = read_local_frame(self.process.stdout, deadline=deadline)
        self.assertIsNotNone(response)
        return decode(response)

    def shape(self, name):
        return ContractValidator({"$ref": f"#/$defs/{name}", "$defs": self.definitions})

    def assert_application(self, value, accepted):
        try:
            expected_result = data_controls.evaluate(value)
            python_accepted = True
        except LocalError:
            expected_result = None
            python_accepted = False
        self.assertEqual(python_accepted, accepted)
        native = self.native(value)
        self.assertEqual(native["accepted"], accepted)
        if accepted:
            self.assertEqual(native["result"], expected_result)

    def test_descriptor_is_self_contained_bounded_and_identical_in_both_languages(self):
        source = (ROOT / "ncp-core/local-profile.v1.json").read_bytes()
        self.assertEqual(source, profile_descriptor_bytes())
        self.assertLessEqual(len(source), 65_536)
        Draft202012Validator.check_schema(self.descriptor["data_schema"])

        def references(value):
            if type(value) is dict:
                for key, child in value.items():
                    if key == "$ref":
                        self.assertTrue(child.startswith("#/$defs/"))
                        self.assertIn(child.removeprefix("#/$defs/"), self.definitions)
                    references(child)
            elif type(value) is list:
                for child in value:
                    references(child)

        references(self.descriptor)
        self.assertEqual(
            self.native({"kind": "profile"})["result"]["digest"], profile_digest()
        )
        identity = json.loads(
            (ROOT / "ncp-core/tests/fixtures/local-profile-identity.json").read_text()
        )
        self.assertEqual(
            hashlib.sha256(source).hexdigest(), identity["descriptor_sha256"]
        )
        self.assertEqual(profile_digest(), identity["typed_profile_digest"])
        binding = LocalBinding.fresh("body")
        old = binding.as_dict()
        old["profile_digest"] = identity["previous_candidate_digest"]
        with self.assertRaises(LocalError):
            LocalBinding.from_dict(old)
        self.assertEqual(LocalBinding.from_dict(binding.as_dict()), binding)

    def test_every_normative_section_changes_identity_and_reordering_does_not(self):
        original = profile_digest()
        for label in ("status", "publication_status", "qualification_status"):
            self.assertNotIn(label, self.descriptor)
            changed = copy.deepcopy(self.descriptor)
            changed[label] = "released"
            binding = LocalBinding.fresh("body").as_dict()
            binding["profile_digest"] = local_digest("ncp.local.profile.v1", changed)
            self.assertNotEqual(binding["profile_digest"], original)
            with self.assertRaises(LocalError):
                LocalBinding.from_dict(binding)
        for key in self.descriptor:
            with self.subTest(section=key):
                changed = copy.deepcopy(self.descriptor)
                del changed[key]
                digest = local_digest("ncp.local.profile.v1", changed)
                self.assertNotEqual(digest, original)
                self.assertEqual(
                    self.native(
                        {
                            "kind": "digest",
                            "domain": "ncp.local.profile.v1",
                            "body": changed,
                        }
                    )["result"]["digest"],
                    digest,
                )
        reordered = dict(reversed(list(self.descriptor.items())))
        self.assertEqual(local_digest("ncp.local.profile.v1", reordered), original)

    def test_named_assertions_have_live_positive_and_negative_native_controls(self):
        controls = {
            name: (value, accepted)
            for name, value, accepted in data_controls.controls()
        }
        identifiers = [row["id"] for row in self.descriptor["semantic_assertions"]]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        for assertion in self.descriptor["semantic_assertions"]:
            self.assertIn(assertion["applies_to"], self.definitions)
            self.assertTrue(assertion["requirement"])
            for field, expected in (
                ("positive_controls", True),
                ("negative_controls", False),
            ):
                self.assertTrue(assertion[field])
                for name in assertion[field]:
                    with self.subTest(assertion=assertion["id"], case=name):
                        self.assertIn(name, controls)
                        value, accepted = controls[name]
                        self.assertEqual(accepted, expected)
                        self.assert_application(value, expected)

    def test_closed_shapes_agree_with_native_application_fields(self):
        types = {
            "plan": "RunPlan",
            "snapshot": "Snapshot",
            "neural": "NeuralProposal",
            "body": "BodyResult",
        }
        for name, value, accepted in data_controls.controls():
            if not accepted:
                continue
            kind = types[value["kind"]]
            validator = self.shape(kind)
            with self.subTest(case=name):
                validator.validate(value["body"])
                self.assert_application(value, True)
            for field in self.definitions[kind]["required"]:
                with self.subTest(case=name, missing=field):
                    changed = copy.deepcopy(value)
                    del changed["body"][field]
                    self.assertFalse(validator.is_valid(changed["body"]))
                    self.assert_application(changed, False)
            changed = copy.deepcopy(value)
            changed["body"]["unexpected_member"] = 0
            self.assertFalse(validator.is_valid(changed["body"]))
            self.assert_application(changed, False)

    def test_numeric_shape_boundaries_are_bound_to_native_validation(self):
        p = data_controls.plan()
        for field in (
            "planned_steps",
            "step_us",
            "resolution_us",
            "readout_delay_us",
            "seed",
        ):
            rule = self.definitions["RunPlan"]["properties"][field]
            for invalid in (
                rule["minimum"] - 1,
                rule["maximum"] + 1,
                True,
                float(p[field]),
            ):
                with self.subTest(field=field, invalid=invalid):
                    changed = copy.deepcopy(p)
                    changed[field] = invalid
                    value = {"kind": "plan", "body": changed}
                    self.assertFalse(self.shape("RunPlan").is_valid(changed))
                    self.assert_application(value, False)
        for field in ("planned_steps", "seed"):
            rule = self.definitions["RunPlan"]["properties"][field]
            for valid in (rule["minimum"], rule["maximum"]):
                changed = copy.deepcopy(p)
                changed[field] = valid
                self.shape("RunPlan").validate(changed)
                self.assert_application({"kind": "plan", "body": changed}, True)

    def test_schema_alone_does_not_claim_causal_or_scientific_validation(self):
        p = data_controls.plan()
        source = data_controls.snapshot(p)
        neural = data_controls.proposal(p, source)
        neural["source_snapshot_digest"] = "0" * 64
        self.shape("NeuralProposal").validate(neural)
        self.assert_application(
            {"kind": "neural", "body": neural, "plan": p, "source": source}, False
        )
        valid = data_controls.proposal(p, source)
        self.assert_application(
            {"kind": "neural", "body": valid, "plan": p, "source": source}, True
        )
        # UTF-8 length is a byte contract. JSON Schema maxLength alone is insufficient.
        value = copy.deepcopy(valid)
        value["neural_model"] = "é" * 33
        self.assertFalse(self.shape("NeuralProposal").is_valid(value))
        self.assert_application(
            {"kind": "neural", "body": value, "plan": p, "source": source}, False
        )
        value["neural_model"] = "é" * 32
        self.shape("NeuralProposal").validate(value)
        self.assert_application(
            {"kind": "neural", "body": value, "plan": p, "source": source}, True
        )

    def test_entire_declared_outcome_matrix_agrees_with_both_native_verifiers(self):
        binding = LocalBinding.fresh("body")
        request = make_request(binding, 1, "prepare", {})
        owner = LocalOwner(binding, EmptyBackend())
        response = decode(owner.handle(encode(request)))
        matrix = self.descriptor["message_contract"]["response_outcomes"]
        properties = self.definitions["LocalResponse"]["properties"]
        for outcome in properties["outcome"]["enum"]:
            for code in properties["code"]["enum"]:
                for operation in properties["operation"]["enum"]:
                    with self.subTest(outcome=outcome, code=code, operation=operation):
                        changed = copy.deepcopy(response)
                        changed.update(outcome=outcome, code=code, operation=operation)
                        changed["result_digest"] = digest_without(
                            "ncp.local.response.v1", changed, "result_digest"
                        )
                        self.shape("LocalResponse").validate(changed)
                        expected = (
                            code in matrix[outcome]["codes"]
                            and operation in matrix[outcome]["operations"]
                            and (
                                operation in self.descriptor["roles"][binding.role]
                                or outcome == "rejected_before_execution"
                                and code == "role"
                            )
                        )
                        try:
                            verify_integrity(changed, binding)
                            python_accepted = True
                        except LocalError:
                            python_accepted = False
                        self.assertEqual(python_accepted, expected)
                        self.assertEqual(
                            self.native(
                                {
                                    "kind": "response",
                                    "binding": binding.as_dict(),
                                    "body": changed,
                                }
                            )["accepted"],
                            expected,
                        )


if __name__ == "__main__":
    unittest.main()
