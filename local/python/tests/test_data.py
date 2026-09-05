"""Application controls and a separate executable Rust differential oracle."""

import copy
import json
import os
from pathlib import Path
import struct
import subprocess
import time
import unittest

from ncp_local import (
    LocalError,
    action_layout,
    decode,
    encode,
    local_digest,
    observation_layout,
    plan_digest,
    profile_digest,
    read_local_frame,
    seal_snapshot,
    validate_body_result,
    validate_neural_proposal,
    validate_plan,
    validate_snapshot,
    write_local_frame,
)


def plan():
    return {
        "schema": "ncp.local.plan.v1",
        "entity_ids": ["a", "b"],
        "planned_steps": 4,
        "step_us": 20_000,
        "resolution_us": 100,
        "readout_delay_us": 1000,
        "seed": 7,
        "execution_mode": "direct_simulation",
        "capture_mode": "lossless_bounded",
        "monitor_mode": "record_only",
        "calibrated_posterior": False,
        "observation_layout": observation_layout(),
        "action_layout": action_layout(),
    }


def snapshot(p, step=0):
    return seal_snapshot(
        {
            "schema": "ncp.local.snapshot.v1",
            "plan_digest": plan_digest(p),
            "step": step,
            "time_us": step * p["step_us"],
            "entity_ids": p["entity_ids"],
            "available": [True, False],
            "values": [0.0] * 12,
            "innovations": [
                {
                    "entity_id": "a",
                    "modality": "visual",
                    "dof": 3,
                    "status": "birth",
                    "nis": None,
                    "source": None,
                },
                {
                    "entity_id": "b",
                    "modality": "visual",
                    "dof": 3,
                    "status": "unavailable",
                    "nis": None,
                    "source": None,
                },
            ],
            "snapshot_digest": "",
        },
        p,
    )


def proposal(p, source):
    return {
        "schema": "ncp.local.neural-result.v1",
        "plan_digest": plan_digest(p),
        "step": source["step"] + 1,
        "source_snapshot_digest": source["snapshot_digest"],
        "selected_modes": ["active", "zero_acceleration"],
        "values": [1.0, -2.0, 3.0, 0.0, 0.0, 0.0],
        "neural_time_us": (source["step"] + 1) * p["step_us"],
        "completed_end_us": (source["step"] + 1) * p["step_us"] - p["readout_delay_us"],
        "window_start_us": max(source["time_us"] - p["readout_delay_us"], 0),
        "spike_counts": [0] * 12,
        "neural_model": "iaf_psc_alpha",
    }


def body_result(p, source):
    return {
        "schema": "ncp.local.body-result.v1",
        "plan_digest": plan_digest(p),
        "step": source["step"] + 1,
        "source_snapshot_digest": source["snapshot_digest"],
        "neural_result_digest": "a" * 64,
        "selected_modes": ["active", "zero_acceleration"],
        "proposed_values": [1.0, -2.0, 3.0, 0.0, 0.0, 0.0],
        "applied_values": [1.0, -2.0, 3.0, 0.0, 0.0, 0.0],
        "saturated": [False, False],
        "snapshot": snapshot(p, source["step"] + 1),
    }


def controls():
    p = plan()
    source = snapshot(p)
    output = []

    def add(name, kind, body, accepted):
        output.append(
            (
                name,
                {
                    "kind": kind,
                    "body": copy.deepcopy(body),
                    "plan": p,
                    "source": source,
                },
                accepted,
            )
        )

    add("valid_plan", "plan", p, True)
    for field, value in [
        ("calibrated_posterior", True),
        ("calibrated_posterior", 0),
        ("execution_mode", "haldir_gated"),
        ("monitor_mode", "deny_tighten"),
        ("capture_mode", "lossy"),
        ("entity_ids", ["b", "a"]),
        ("entity_ids", ["a", "a"]),
        ("entity_ids", []),
        ("entity_ids", ["a", "b", "c", "d"]),
        ("entity_ids", ["../a"]),
        ("planned_steps", 1025),
        ("planned_steps", 0),
        ("planned_steps", 4.0),
        ("seed", True),
        ("seed", 0),
        ("resolution_us", 333),
        ("step_us", 20_001),
        ("readout_delay_us", 20_000),
        ("readout_delay_us", 0),
        ("readout_delay_us", 101),
    ]:
        changed = copy.deepcopy(p)
        changed[field] = value
        add(f"plan_{field}_{value}", "plan", changed, False)
    changed = copy.deepcopy(p)
    changed["observation_layout"][0]["unit"] = "mm"
    add("layout_unit_drift", "plan", changed, False)
    changed = copy.deepcopy(p)
    changed["action_layout"].reverse()
    add("layout_axis_drift", "plan", changed, False)
    changed = copy.deepcopy(p)
    changed["unknown"] = 0
    add("plan_unknown_field", "plan", changed, False)

    add("valid_missing_snapshot", "snapshot", source, True)
    omitted = copy.deepcopy(source)
    for innovation in omitted["innovations"]:
        del innovation["nis"]
        del innovation["source"]
    add("typed_optional_null_projection", "snapshot", omitted, True)
    observed = copy.deepcopy(source)
    observed["innovations"][0].update(
        {
            "status": "observed",
            "nis": 0.0,
            "source": {
                "sensor_id": "visual-a",
                "fusion_track_id": 1,
                "fusion_sequence": 1,
                "measurement_time_us": 0,
                "residual_m": [0.0, 0.0, 0.0],
                "covariance_m2": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            },
        }
    )
    observed = seal_snapshot(observed, p)
    add("observed_zero_nis_with_actual_source", "snapshot", observed, True)
    for name, mutate in [
        ("missing_is_nonzero", lambda v: v["values"].__setitem__(6, 1.0)),
        ("truncated_vector", lambda v: v["values"].pop()),
        ("wrong_time", lambda v: v.__setitem__("time_us", 1)),
        ("boolean_time", lambda v: v.__setitem__("time_us", False)),
        (
            "birth_is_not_observed_zero",
            lambda v: v["innovations"][0].__setitem__("nis", 0.0),
        ),
        (
            "unavailable_is_not_observed_zero",
            lambda v: v["innovations"][1].__setitem__("nis", 0.0),
        ),
        (
            "missing_source_for_observed",
            lambda v: v["innovations"][0].__setitem__("status", "observed"),
        ),
        ("wrong_roster", lambda v: v["entity_ids"].reverse()),
        ("availability_must_be_bool", lambda v: v["available"].__setitem__(0, 1)),
        (
            "forged_snapshot_digest",
            lambda v: v.__setitem__("snapshot_digest", "0" * 64),
        ),
    ]:
        changed = copy.deepcopy(source)
        mutate(changed)
        add(name, "snapshot", changed, False)
    for name, mutate in [
        (
            "observed_without_source",
            lambda v: v["innovations"][0].__setitem__("source", None),
        ),
        (
            "wrong_measurement_time",
            lambda v: v["innovations"][0]["source"].__setitem__(
                "measurement_time_us", 1
            ),
        ),
        (
            "truncated_covariance",
            lambda v: v["innovations"][0]["source"]["covariance_m2"].pop(),
        ),
        (
            "wrong_degrees_of_freedom",
            lambda v: v["innovations"][0].__setitem__("dof", 2),
        ),
    ]:
        changed = copy.deepcopy(observed)
        mutate(changed)
        add(name, "snapshot", changed, False)

    neural = proposal(p, source)
    add("valid_proposal_and_real_silence", "neural", neural, True)
    for name, field, value in [
        ("future_step", "step", 2),
        ("wrong_source_digest", "source_snapshot_digest", "0" * 64),
        ("future_readout", "completed_end_us", 20_000),
        ("reused_window", "window_start_us", 1),
        ("truncated_readout", "spike_counts", [0] * 11),
        ("readout_float", "spike_counts", [0.0] * 12),
        ("unavailable_lane_active", "selected_modes", ["active", "active"]),
        ("unknown_mode", "selected_modes", ["hold", "zero_acceleration"]),
        ("unbounded_action", "values", [51.0, 0, 0, 0, 0, 0]),
        ("noninert_missing_lane", "values", [0, 0, 0, 1, 0, 0]),
    ]:
        changed = copy.deepcopy(neural)
        changed[field] = value
        add(name, "neural", changed, False)

    body = body_result(p, source)
    add("valid_body_result", "body", body, True)
    for field, value in [
        ("step", 0),
        ("step", 2),
        ("saturated", [False]),
        ("saturated", [0, False]),
        ("neural_result_digest", "not_a_digest"),
        ("applied_values", [1, -2, 3, 1, 0, 0]),
        ("selected_modes", ["active"]),
        ("proposed_values", [1, -2, 3]),
    ]:
        changed = copy.deepcopy(body)
        changed[field] = value
        add(f"body_{field}_{value}", "body", changed, False)
    return output


def evaluate(value):
    kind, body = value["kind"], value["body"]
    if kind == "plan":
        validate_plan(body)
        return {"digest": plan_digest(body)}
    if kind == "snapshot":
        validate_snapshot(body, value["plan"])
        return {"digest": body["snapshot_digest"]}
    if kind == "neural":
        validate_neural_proposal(body, value["plan"], value["source"])
        return {}
    validate_body_result(body, value["plan"])
    return {}


class DataTests(unittest.TestCase):
    def test_positive_and_negative_application_controls(self):
        for name, value, expected in controls():
            with self.subTest(case=name):
                if expected:
                    evaluate(value)
                else:
                    with self.assertRaises(LocalError):
                        evaluate(value)

    def test_sealing_preserves_input_and_does_not_approve_missingness(self):
        p = plan()
        source = snapshot(p)
        source["snapshot_digest"] = ""
        sealed = seal_snapshot(source, p)
        self.assertEqual(source["snapshot_digest"], "")
        validate_snapshot(sealed, p)
        source["values"][6] = 1.0
        with self.assertRaises(LocalError):
            seal_snapshot(source, p)

    def test_frozen_binary64_vectors(self):
        vectors = json.loads(
            (
                Path(__file__).resolve().parents[3]
                / "ncp-core/tests/fixtures/local-binary64.json"
            ).read_text()
        )
        for case in vectors["cases"]:
            with self.subTest(case=case["id"]):
                value = decode(case["decimal"].encode())
                self.assertEqual(struct.pack(">d", float(value)).hex(), case["bits"])
                self.assertEqual(local_digest(vectors["domain"], value), case["digest"])

    @unittest.skipUnless(
        os.environ.get("NCP_LOCAL_CONTRACT_PROBE"),
        "set NCP_LOCAL_CONTRACT_PROBE for installed Rust/Python differential gate",
    )
    def test_independent_rust_executable_agrees_on_all_controls(self):
        process = subprocess.Popen(
            [os.environ["NCP_LOCAL_CONTRACT_PROBE"]],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        try:
            for name, value, expected in controls():
                with self.subTest(case=name):
                    deadline = time.monotonic() + 5
                    write_local_frame(process.stdin, encode(value), deadline=deadline)
                    result = decode(read_local_frame(process.stdout, deadline=deadline))
                    self.assertEqual(result["accepted"], expected)
                    if expected:
                        self.assertEqual(result["result"], evaluate(value))
            write_local_frame(process.stdin, encode({"kind": "profile"}))
            self.assertEqual(
                decode(read_local_frame(process.stdout))["result"]["digest"],
                profile_digest(),
            )
            process.stdin.close()
            process.wait(timeout=5)
            self.assertEqual(process.returncode, 0, process.stderr.read().decode())
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()


if __name__ == "__main__":
    unittest.main()
