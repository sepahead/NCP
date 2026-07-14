from __future__ import annotations

import io
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from e2e import nest_five_networks as nest_runner
from e2e import run_cross_language_e2e as cross_runner


class CrossLanguageRunnerStatusTests(unittest.TestCase):
    def test_missing_engram_checkout_is_not_run_and_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as directory, io.StringIO() as output:
            with redirect_stdout(output):
                status = cross_runner.main(["--engram", directory])
            rendered = output.getvalue()

        self.assertEqual(status, cross_runner.NOT_RUN)
        self.assertIn("RESULT: NOT RUN", rendered)
        self.assertNotIn("RESULT: PASS", rendered)
        self.assertNotIn("SKIP", rendered)

    def test_legacy_bridge_file_presence_is_not_compatibility_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bridge = Path(directory) / cross_runner.ENGRAM_BRIDGE
            bridge.parent.mkdir(parents=True)
            bridge.write_text("# historical fixture\n", encoding="utf-8")
            with io.StringIO() as output, redirect_stdout(output):
                status = cross_runner.main(["--engram", directory])
                rendered = output.getvalue()

        self.assertEqual(status, cross_runner.NOT_RUN)
        self.assertIn("file presence does not establish a native-1.0 SessionService", rendered)
        self.assertNotIn("RESULT: PASS", rendered)


class NestRunnerStatusTests(unittest.TestCase):
    def test_all_five_successful_scenarios_pass_local_smoke(self) -> None:
        results = [{"ok": True, "model": model} for model in nest_runner.REQUIRED_MODELS]
        self.assertEqual(nest_runner._result_status(results), ("PASS", nest_runner.PASS))

    def test_partial_successful_scenario_set_is_not_run(self) -> None:
        results = [
            {"ok": True, "model": model} for model in nest_runner.REQUIRED_MODELS[:-1]
        ]
        self.assertEqual(
            nest_runner._result_status(results), ("NOT RUN", nest_runner.NOT_RUN)
        )

    def test_attempted_scenario_failure_is_fail(self) -> None:
        results = [
            {"ok": True, "model": nest_runner.REQUIRED_MODELS[0]},
            {"ok": False, "model": nest_runner.REQUIRED_MODELS[1]},
        ]
        self.assertEqual(nest_runner._result_status(results), ("FAIL", nest_runner.FAIL))

    def test_duplicate_model_cannot_replace_a_required_scenario(self) -> None:
        models = list(nest_runner.REQUIRED_MODELS)
        models[-1] = models[0]
        results = [{"ok": True, "model": model} for model in models]
        self.assertEqual(
            nest_runner._result_status(results), ("NOT RUN", nest_runner.NOT_RUN)
        )

    def test_receipt_rejects_non_hexadecimal_result_digest(self) -> None:
        request = {
            "operation": {
                "operation_id": "123e4567-e89b-42d3-a456-426614174010",
                "request_digest": "a" * 64,
            }
        }
        reply = {
            "receipt": {
                "operation_id": request["operation"]["operation_id"],
                "request_digest": request["operation"]["request_digest"],
                "outcome": "succeeded",
                "result_digest": "z" * 64,
                "state_version": 2,
                "committed_at_utc_ms": 1_000,
                "responder_principal_id": "body",
                "responder_entity_id": "plant",
            }
        }
        with self.assertRaisesRegex(RuntimeError, "lowercase SHA-256"):
            nest_runner._receipt(reply, request, 1)

    def test_preprovisioned_authority_is_read_from_session_opened(self) -> None:
        generation = "123e4567-e89b-42d3-a456-426614174000"
        issued = int(time.time() * 1000)
        authority = {
            "session_epoch": generation,
            "term": 1,
            "lease_id": "123e4567-e89b-42d3-a456-426614174001",
            "issuer_principal_id": "local-body",
            "holder_principal_id": nest_runner.COMMANDER_PRINCIPAL,
            "holder_entity_id": nest_runner.COMMANDER_ENTITY,
            "issued_at_utc_ms": issued,
            "expires_at_utc_ms": issued + 60_000,
        }
        opened = {"dev_smoke_authority": authority}
        self.assertIs(nest_runner._preprovisioned_authority(opened, generation), authority)

    def test_preprovisioned_authority_rejects_unknown_fields_and_bad_generation(self) -> None:
        generation = "123e4567-e89b-42d3-a456-426614174000"
        issued = int(time.time() * 1000)
        authority = {
            "session_epoch": generation,
            "term": 1,
            "lease_id": "123e4567-e89b-42d3-a456-426614174001",
            "issuer_principal_id": "local-body",
            "holder_principal_id": nest_runner.COMMANDER_PRINCIPAL,
            "holder_entity_id": nest_runner.COMMANDER_ENTITY,
            "issued_at_utc_ms": issued,
            "expires_at_utc_ms": issued + 60_000,
            "unexpected": True,
        }
        with self.assertRaisesRegex(RuntimeError, "exact lease shape"):
            nest_runner._preprovisioned_authority(
                {"dev_smoke_authority": authority}, generation
            )
        authority.pop("unexpected")
        with self.assertRaisesRegex(RuntimeError, "canonical lowercase UUIDv4"):
            nest_runner._preprovisioned_authority(
                {"dev_smoke_authority": authority}, "not-a-generation"
            )

    def test_receipt_rejects_unsafe_state_and_missing_commit_timestamp(self) -> None:
        request = {
            "operation": {
                "operation_id": "123e4567-e89b-42d3-a456-426614174010",
                "request_digest": "a" * 64,
            }
        }
        receipt = {
            "operation_id": request["operation"]["operation_id"],
            "request_digest": request["operation"]["request_digest"],
            "outcome": "succeeded",
            "result_digest": "b" * 64,
            "state_version": nest_runner.SAFE_INTEGER_MAX + 1,
            "responder_principal_id": "body",
            "responder_entity_id": "plant",
        }
        with self.assertRaisesRegex(RuntimeError, "state_version"):
            nest_runner._receipt({"receipt": receipt}, request, 1)
        receipt["state_version"] = 2
        with self.assertRaisesRegex(RuntimeError, "commit timestamp"):
            nest_runner._receipt({"receipt": receipt}, request, 1)

    def test_receipt_rejects_control_character_in_responder_identity(self) -> None:
        request = {
            "operation": {
                "operation_id": "123e4567-e89b-42d3-a456-426614174010",
                "request_digest": "a" * 64,
            }
        }
        receipt = {
            "operation_id": request["operation"]["operation_id"],
            "request_digest": request["operation"]["request_digest"],
            "outcome": "succeeded",
            "result_digest": "b" * 64,
            "state_version": 2,
            "committed_at_utc_ms": 1_000,
            "responder_principal_id": "body\u007f",
            "responder_entity_id": "plant",
        }
        with self.assertRaisesRegex(RuntimeError, "responder identity"):
            nest_runner._receipt({"receipt": receipt}, request, 1)

    def test_missing_native_service_is_not_run_and_nonzero(self) -> None:
        refusal = ConnectionRefusedError("connection refused")
        with mock.patch.object(nest_runner.socket, "create_connection", side_effect=refusal):
            with io.StringIO() as output, redirect_stdout(output):
                status = nest_runner.main()
                rendered = output.getvalue()

        self.assertEqual(status, nest_runner.NOT_RUN)
        self.assertIn("LOCAL SMOKE RESULT: NOT RUN", rendered)
        self.assertNotIn("LOCAL SMOKE RESULT: PASS", rendered)

    def test_non_loopback_dev_endpoint_fails_before_connection(self) -> None:
        with (
            mock.patch.object(nest_runner, "HOST", "192.0.2.1"),
            mock.patch.object(nest_runner.socket, "create_connection") as connect,
            io.StringIO() as output,
            redirect_stdout(output),
        ):
            status = nest_runner.main()
            rendered = output.getvalue()

        self.assertEqual(status, nest_runner.FAIL)
        self.assertIn("LOCAL SMOKE RESULT: FAIL", rendered)
        connect.assert_not_called()

    def test_scoped_ipv6_loopback_fails_before_connection(self) -> None:
        with (
            mock.patch.object(nest_runner, "HOST", "::1%lo0"),
            mock.patch.object(nest_runner.socket, "create_connection") as connect,
            io.StringIO() as output,
            redirect_stdout(output),
        ):
            status = nest_runner.main()
            rendered = output.getvalue()

        self.assertEqual(status, nest_runner.FAIL)
        self.assertIn("LOCAL SMOKE RESULT: FAIL", rendered)
        connect.assert_not_called()

    def test_malformed_security_digest_fails_before_connection(self) -> None:
        with (
            mock.patch.object(nest_runner, "SECURITY_STATE_DIGEST", "not-a-digest"),
            mock.patch.object(nest_runner.socket, "create_connection") as connect,
            io.StringIO() as output,
            redirect_stdout(output),
        ):
            status = nest_runner.main()
            rendered = output.getvalue()

        self.assertEqual(status, nest_runner.FAIL)
        self.assertIn("LOCAL SMOKE RESULT: FAIL", rendered)
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
