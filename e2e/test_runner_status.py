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
        self.assertIn(
            "file presence does not establish a native-1.0 SessionService", rendered
        )
        self.assertNotIn("RESULT: PASS", rendered)


class NestRunnerStatusTests(unittest.TestCase):
    RESPONDER = ("body", "plant")

    def test_closed_loop_control_uses_prior_error_and_saturates(self) -> None:
        case = nest_runner.ClosedLoopCase(
            "test", "iaf_psc_alpha", 10, 500.0, 20, 10.0, 0.0, 600.0
        )

        self.assertEqual(nest_runner._next_control(case, 500.0, 15), (5, 550.0))
        self.assertEqual(nest_runner._next_control(case, 500.0, 0), (20, 600.0))
        self.assertEqual(nest_runner._next_control(case, 100.0, 40), (-20, 0.0))

    def test_spike_observation_requires_exact_series_and_simulation_advance(
        self,
    ) -> None:
        observation = {
            "sim_time_ms": 100.0,
            "records": {
                "spk": {
                    "port": "spk",
                    "target": "pop",
                    "observable": "spikes",
                    "times": [1.0, 2.0],
                    "values": [],
                    "senders": [1, 2],
                }
            },
        }

        self.assertEqual(
            nest_runner._spike_observation(observation, 0.0, 100.0),
            (2, 100.0),
        )
        observation["records"]["unexpected"] = {}
        with self.assertRaisesRegex(RuntimeError, "exactly the negotiated"):
            nest_runner._spike_observation(observation, 0.0, 100.0)

    def test_spike_observation_rejects_stale_or_unsorted_interval_data(self) -> None:
        observation = {
            "sim_time_ms": 200.0,
            "records": {
                "spk": {
                    "port": "spk",
                    "target": "pop",
                    "observable": "spikes",
                    "times": [100.0, 150.0],
                    "values": [],
                    "senders": [1, 2],
                }
            },
        }
        with self.assertRaisesRegex(RuntimeError, "newly advanced interval"):
            nest_runner._spike_observation(observation, 100.0, 200.0)
        observation["records"]["spk"]["times"] = [175.0, 150.0]
        with self.assertRaisesRegex(RuntimeError, "non-decreasing"):
            nest_runner._spike_observation(observation, 100.0, 200.0)

    def test_spike_observation_requires_positive_parallel_nest_senders(self) -> None:
        observation = {
            "sim_time_ms": 100.0,
            "records": {
                "spk": {
                    "port": "spk",
                    "target": "pop",
                    "observable": "spikes",
                    "times": [25.0],
                    "values": [],
                }
            },
        }
        with self.assertRaisesRegex(RuntimeError, "sender and time arrays disagree"):
            nest_runner._spike_observation(observation, 0.0, 100.0)
        observation["records"]["spk"]["senders"] = [0]
        with self.assertRaisesRegex(RuntimeError, "positive JSON-safe NEST node ID"):
            nest_runner._spike_observation(observation, 0.0, 100.0)

    def test_spike_observation_rejects_noncanonical_series_shape(self) -> None:
        record = {
            "port": "spk",
            "target": "pop",
            "observable": "spikes",
            "times": [],
            "values": None,
            "senders": [],
        }
        observation = {"sim_time_ms": 100.0, "records": {"spk": record}}
        with self.assertRaisesRegex(RuntimeError, "scalar values"):
            nest_runner._spike_observation(observation, 0.0, 100.0)

        record["values"] = []
        record["unexpected"] = True
        with self.assertRaisesRegex(RuntimeError, "unknown member"):
            nest_runner._spike_observation(observation, 0.0, 100.0)

        record.pop("unexpected")
        record["unit"] = "mV"
        with self.assertRaisesRegex(RuntimeError, "unit or recordable"):
            nest_runner._spike_observation(observation, 0.0, 100.0)

    def test_observation_stream_is_fresh_and_stays_in_one_epoch(self) -> None:
        epoch = "123e4567-e89b-42d3-a456-426614174000"
        first = {"stream": {"epoch": epoch, "seq": 2}}
        second = {"stream": {"epoch": epoch, "seq": 4}}
        position = nest_runner._observation_stream(first, None)
        self.assertEqual(position, (epoch, 2))
        self.assertEqual(nest_runner._observation_stream(second, position), (epoch, 4))
        with self.assertRaisesRegex(RuntimeError, "replayed, or regressed"):
            nest_runner._observation_stream(first, position)

    def test_observation_stream_rejects_foreign_epoch_after_first_position(
        self,
    ) -> None:
        epoch = "123e4567-e89b-42d3-a456-426614174000"
        other = "223e4567-e89b-42d3-a456-426614174000"
        position = nest_runner._observation_stream(
            {"stream": {"epoch": epoch, "seq": 7}}, None
        )
        with self.assertRaisesRegex(RuntimeError, "changed epoch"):
            nest_runner._observation_stream(
                {"stream": {"epoch": other, "seq": 8}}, position
            )

    def test_all_five_successful_scenarios_pass_local_smoke(self) -> None:
        results = [
            {"ok": True, "model": model} for model in nest_runner.REQUIRED_MODELS
        ]
        self.assertEqual(
            nest_runner._result_status(results), ("PASS", nest_runner.PASS)
        )

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
        self.assertEqual(
            nest_runner._result_status(results), ("FAIL", nest_runner.FAIL)
        )

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
            nest_runner._receipt(reply, request, 1, self.RESPONDER)

    def test_receipt_responder_must_match_the_opened_body(self) -> None:
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
                "result_digest": "b" * 64,
                "state_version": 2,
                "committed_at_utc_ms": 1_000,
                "responder_principal_id": "other-body",
                "responder_entity_id": "plant",
            }
        }
        with self.assertRaisesRegex(RuntimeError, "body coordinate carried by open"):
            nest_runner._receipt(reply, request, 1, self.RESPONDER)

    def test_session_opened_establishes_an_exact_body_identity(self) -> None:
        opened = {
            "identity": {
                "principal_id": "body",
                "entity_id": "plant",
                "role": "body",
                "plane": "control",
            }
        }
        self.assertEqual(nest_runner._responder_identity(opened), self.RESPONDER)
        opened["identity"]["role"] = "observer"
        with self.assertRaisesRegex(RuntimeError, "control-plane body"):
            nest_runner._responder_identity(opened)

    def test_session_opened_binds_exact_model_population_and_provenance(self) -> None:
        case = nest_runner.ClosedLoopCase(
            "test", "iaf_psc_alpha", 10, 500.0, 20, 10.0, 0.0, 600.0
        )
        opened = {
            "backend": "nest",
            "resolved": {"pop": 10},
            "provenance": {
                "network_ref": "iaf_psc_alpha",
                "backend": "nest",
                "calibrated_posterior": False,
                "is_simulation_output": True,
                "advisory_only": True,
            },
        }
        self.assertEqual(nest_runner._resolved_execution(opened, case), "nest")
        opened["resolved"]["pop"] = 9
        with self.assertRaisesRegex(RuntimeError, "resolved population"):
            nest_runner._resolved_execution(opened, case)

    def test_session_opened_rejects_non_nest_or_unknown_provenance(self) -> None:
        case = nest_runner.ClosedLoopCase(
            "test", "iaf_psc_alpha", 10, 500.0, 20, 10.0, 0.0, 600.0
        )
        opened = {
            "backend": "mock",
            "resolved": {"pop": 10},
            "provenance": {
                "network_ref": "iaf_psc_alpha",
                "backend": "mock",
                "calibrated_posterior": False,
                "is_simulation_output": True,
                "advisory_only": True,
            },
        }
        with self.assertRaisesRegex(RuntimeError, "required NEST backend"):
            nest_runner._resolved_execution(opened, case)

        opened["backend"] = "nest"
        opened["provenance"]["backend"] = "nest"
        opened["provenance"]["certified"] = True
        with self.assertRaisesRegex(RuntimeError, "requested execution"):
            nest_runner._resolved_execution(opened, case)

    def test_session_opened_rejects_malformed_optional_provenance(self) -> None:
        case = nest_runner.ClosedLoopCase(
            "test", "iaf_psc_alpha", 10, 500.0, 20, 10.0, 0.0, 600.0
        )
        opened = {
            "backend": "nest",
            "resolved": {"pop": 10},
            "provenance": {
                "network_ref": "iaf_psc_alpha",
                "backend": "nest",
                "seed": True,
                "calibrated_posterior": False,
                "is_simulation_output": True,
                "advisory_only": True,
            },
        }
        with self.assertRaisesRegex(RuntimeError, "seed is not a JSON-safe integer"):
            nest_runner._resolved_execution(opened, case)
        opened["provenance"]["seed"] = 1
        opened["provenance"]["note"] = 7
        with self.assertRaisesRegex(RuntimeError, "note is not a string or null"):
            nest_runner._resolved_execution(opened, case)

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
        self.assertIs(
            nest_runner._preprovisioned_authority(opened, generation), authority
        )

    def test_preprovisioned_authority_rejects_unknown_fields_and_bad_generation(
        self,
    ) -> None:
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

    def test_preprovisioned_authority_rejects_future_issuance(self) -> None:
        generation = "123e4567-e89b-42d3-a456-426614174000"
        now = int(time.time() * 1000)
        authority = {
            "session_epoch": generation,
            "term": 1,
            "lease_id": "123e4567-e89b-42d3-a456-426614174001",
            "issuer_principal_id": "local-body",
            "holder_principal_id": nest_runner.COMMANDER_PRINCIPAL,
            "holder_entity_id": nest_runner.COMMANDER_ENTITY,
            "issued_at_utc_ms": now + 10_000,
            "expires_at_utc_ms": now + 20_000,
        }
        with self.assertRaisesRegex(RuntimeError, "interval is invalid"):
            nest_runner._preprovisioned_authority(
                {"dev_smoke_authority": authority}, generation
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
            nest_runner._receipt({"receipt": receipt}, request, 1, self.RESPONDER)
        receipt["state_version"] = 2
        with self.assertRaisesRegex(RuntimeError, "commit timestamp"):
            nest_runner._receipt({"receipt": receipt}, request, 1, self.RESPONDER)

    def test_receipt_adopts_equal_state_and_rejects_regression(self) -> None:
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
            "state_version": 7,
            "committed_at_utc_ms": 1_000,
            "responder_principal_id": "body",
            "responder_entity_id": "plant",
        }
        self.assertEqual(
            nest_runner._receipt({"receipt": receipt}, request, 7, self.RESPONDER),
            7,
        )
        with self.assertRaisesRegex(RuntimeError, "precedes"):
            nest_runner._receipt({"receipt": receipt}, request, 8, self.RESPONDER)

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
            nest_runner._receipt({"receipt": receipt}, request, 1, self.RESPONDER)

    def test_missing_native_service_is_not_run_and_nonzero(self) -> None:
        refusal = ConnectionRefusedError("connection refused")
        with mock.patch.object(
            nest_runner.socket, "create_connection", side_effect=refusal
        ):
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

    def test_invalid_control_interval_fails_before_connection(self) -> None:
        with (
            mock.patch.object(nest_runner, "ADVANCE_MS", float("nan")),
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
