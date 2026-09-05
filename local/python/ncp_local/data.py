"""Independent closed-schema checks for the local simulation data plane.

Times use integer microseconds. Entity-major vectors use east/north/up SI units.
These checks establish bounded representation and joins, not scientific truth.
"""

from __future__ import annotations

import copy
import math
import re
from typing import Any

from .protocol import valid_digest
from .wire import LocalError, MAX_SEQUENCE, digest_without, local_digest

MAX_STEPS = 1024
MAX_ENTITIES = 3
_ENTITY_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_PLAN_KEYS = frozenset(
    {
        "schema",
        "entity_ids",
        "planned_steps",
        "step_us",
        "resolution_us",
        "readout_delay_us",
        "seed",
        "execution_mode",
        "capture_mode",
        "monitor_mode",
        "calibrated_posterior",
        "observation_layout",
        "action_layout",
    }
)
_SNAPSHOT_KEYS = frozenset(
    {
        "schema",
        "plan_digest",
        "step",
        "time_us",
        "entity_ids",
        "available",
        "values",
        "innovations",
        "snapshot_digest",
    }
)
_INNOVATION_KEYS = frozenset(
    {"entity_id", "modality", "dof", "status", "nis", "source"}
)
_SOURCE_KEYS = frozenset(
    {
        "sensor_id",
        "fusion_track_id",
        "fusion_sequence",
        "measurement_time_us",
        "residual_m",
        "covariance_m2",
    }
)
_NEURAL_KEYS = frozenset(
    {
        "schema",
        "plan_digest",
        "step",
        "source_snapshot_digest",
        "selected_modes",
        "values",
        "neural_time_us",
        "completed_end_us",
        "window_start_us",
        "spike_counts",
        "neural_model",
    }
)
_BODY_KEYS = frozenset(
    {
        "schema",
        "plan_digest",
        "step",
        "source_snapshot_digest",
        "neural_result_digest",
        "selected_modes",
        "proposed_values",
        "applied_values",
        "saturated",
        "snapshot",
    }
)


def _reject() -> None:
    raise LocalError("invalid_input")


def _object(
    value: Any, keys: frozenset[str], optional: frozenset[str] = frozenset()
) -> None:
    if type(value) is not dict or not keys - optional <= set(value) <= keys:
        _reject()


def _integer(value: Any, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _number(value: Any, low: float, high: float) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _vector(value: Any, length: int, low: float, high: float) -> bool:
    return (
        type(value) is list
        and len(value) == length
        and all(_number(item, low, high) for item in value)
    )


def _booleans(value: Any, length: int) -> bool:
    return (
        type(value) is list
        and len(value) == length
        and all(type(item) is bool for item in value)
    )


def _modes(value: Any, length: int) -> bool:
    return (
        type(value) is list
        and len(value) == length
        and all(
            type(item) is str and item in {"active", "zero_acceleration"}
            for item in value
        )
    )


def _components(quantity: str, unit: str) -> list[dict[str, str]]:
    return [
        {"quantity": quantity, "unit": unit, "axis": axis, "frame": "enu"}
        for axis in ("east", "north", "up")
    ]


def observation_layout() -> list[dict[str, str]]:
    return _components("position", "m") + _components("velocity", "m/s")


def action_layout() -> list[dict[str, str]]:
    return _components("acceleration", "m/s^2")


def validate_plan(plan: Any) -> None:
    """Require the exact joint plan, component order, and supported clock grid."""
    _object(plan, _PLAN_KEYS)
    ids = plan["entity_ids"]
    if (
        plan["schema"] != "ncp.local.plan.v1"
        or type(ids) is not list
        or not 1 <= len(ids) <= MAX_ENTITIES
        or not all(type(item) is str and _ENTITY_ID.fullmatch(item) for item in ids)
        or any(left >= right for left, right in zip(ids, ids[1:]))
        or not _integer(plan["planned_steps"], 1, MAX_STEPS)
        or not _integer(plan["step_us"], 1000, 1_000_000)
        or plan["step_us"] % 1000 != 0
        or not _integer(plan["resolution_us"], 1, 1000)
        or plan["step_us"] % plan["resolution_us"] != 0
        or not _integer(
            plan["readout_delay_us"], plan["resolution_us"], plan["step_us"] - 1
        )
        or plan["readout_delay_us"] % plan["resolution_us"] != 0
        or not _integer(plan["seed"], 1, 2_147_483_647)
        or plan["execution_mode"] != "direct_simulation"
        or plan["capture_mode"] != "lossless_bounded"
        or plan["monitor_mode"] != "record_only"
        or plan["calibrated_posterior"] is not False
        or plan["observation_layout"] != observation_layout()
        or plan["action_layout"] != action_layout()
    ):
        _reject()


def plan_digest(plan: Any) -> str:
    validate_plan(plan)
    return local_digest("ncp.local.plan.v1", plan)


def plan_time_us(plan: Any, step: int) -> int:
    validate_plan(plan)
    if not _integer(step, 0, plan["planned_steps"]):
        _reject()
    return step * plan["step_us"]


def validate_prepare(body: Any, *, application_profile: str) -> None:
    """Check the shared envelope. The installed backend owns configuration checks."""
    _object(body, frozenset({"plan", "application_profile", "configuration"}))
    validate_plan(body["plan"])
    if body["application_profile"] != application_profile:
        _reject()


def _validate_source(source: Any, time_us: int) -> None:
    _object(source, _SOURCE_KEYS)
    sensor = source["sensor_id"]
    if (
        type(sensor) is not str
        or not 1 <= len(sensor) <= 128
        or len(sensor.encode("utf-8")) > 128
        or not _integer(source["fusion_track_id"], 0, MAX_SEQUENCE)
        or not _integer(source["fusion_sequence"], 0, MAX_SEQUENCE)
        or not _integer(source["measurement_time_us"], 0, MAX_SEQUENCE)
        or source["measurement_time_us"] != time_us
        or not _vector(source["residual_m"], 3, -200_000, 200_000)
        or type(source["covariance_m2"]) is not list
        or len(source["covariance_m2"]) != 3
        or not all(_vector(row, 3, -1e12, 1e12) for row in source["covariance_m2"])
    ):
        _reject()


def _validate_snapshot_content(snapshot: Any, plan: Any) -> None:
    validate_plan(plan)
    _object(snapshot, _SNAPSHOT_KEYS)
    n = len(plan["entity_ids"])
    if (
        snapshot["schema"] != "ncp.local.snapshot.v1"
        or snapshot["plan_digest"] != plan_digest(plan)
        or not _integer(snapshot["step"], 0, plan["planned_steps"])
        or not _integer(snapshot["time_us"], 0, MAX_SEQUENCE)
        or snapshot["time_us"] != plan_time_us(plan, snapshot["step"])
        or snapshot["entity_ids"] != plan["entity_ids"]
        or not _booleans(snapshot["available"], n)
        or type(snapshot["values"]) is not list
        or len(snapshot["values"]) != n * 6
        or type(snapshot["innovations"]) is not list
        or len(snapshot["innovations"]) != n
        or type(snapshot["snapshot_digest"]) is not str
    ):
        _reject()
    for index, innovation in enumerate(snapshot["innovations"]):
        values = snapshot["values"][index * 6 : (index + 1) * 6]
        available = snapshot["available"][index]
        if (
            not _vector(values[:3], 3, -100_000, 100_000)
            or not _vector(values[3:], 3, -100, 100)
            or (not available and any(value != 0 for value in values))
        ):
            _reject()
        # Rust Option fields admit omission and project it to explicit null.
        _object(innovation, _INNOVATION_KEYS, frozenset({"nis", "source"}))
        if (
            innovation["entity_id"] != plan["entity_ids"][index]
            or innovation["modality"] != "visual"
            or not _integer(innovation["dof"], 3, 3)
            or type(innovation["status"]) is not str
        ):
            _reject()
        status, nis, source = (
            innovation["status"],
            innovation.get("nis"),
            innovation.get("source"),
        )
        if status == "observed":
            if not available or not _number(nis, 0, 1e12):
                _reject()
            _validate_source(source, snapshot["time_us"])
        elif status == "birth":
            if not available or nis is not None or source is not None:
                _reject()
        elif status == "unavailable":
            if nis is not None or source is not None:
                _reject()
        else:
            _reject()


def _snapshot_projection(snapshot: dict[str, Any]) -> dict[str, Any]:
    projection = dict(snapshot)
    projection["innovations"] = [
        dict(item, nis=item.get("nis"), source=item.get("source"))
        for item in snapshot["innovations"]
    ]
    return projection


def validate_snapshot(snapshot: Any, plan: Any) -> None:
    """Require source time, roster, explicit missingness, and a complete digest."""
    _validate_snapshot_content(snapshot, plan)
    if snapshot["snapshot_digest"] != digest_without(
        "ncp.local.snapshot.v1", _snapshot_projection(snapshot), "snapshot_digest"
    ):
        raise LocalError("binding")


def seal_snapshot(snapshot: Any, plan: Any) -> dict[str, Any]:
    """Return a validated sealed copy. Caller-owned source data stays unchanged."""
    _validate_snapshot_content(snapshot, plan)
    sealed = copy.deepcopy(_snapshot_projection(snapshot))
    sealed["snapshot_digest"] = digest_without(
        "ncp.local.snapshot.v1", sealed, "snapshot_digest"
    )
    return sealed


def validate_neural_proposal(result: Any, plan: Any, source: Any) -> None:
    """Join one proposal to its source and exact completed readout interval."""
    validate_snapshot(source, plan)
    _object(result, _NEURAL_KEYS)
    n = len(plan["entity_ids"])
    model = result["neural_model"]
    if (
        result["schema"] != "ncp.local.neural-result.v1"
        or result["plan_digest"] != plan_digest(plan)
        or not _integer(result["step"], 1, plan["planned_steps"])
        or result["step"] != source["step"] + 1
        or result["source_snapshot_digest"] != source["snapshot_digest"]
        or not _integer(result["neural_time_us"], 0, MAX_SEQUENCE)
        or result["neural_time_us"] != plan_time_us(plan, result["step"])
        or not _integer(result["completed_end_us"], 0, MAX_SEQUENCE)
        or result["completed_end_us"]
        != result["neural_time_us"] - plan["readout_delay_us"]
        or not _integer(result["window_start_us"], 0, MAX_SEQUENCE)
        or result["window_start_us"]
        != max(source["time_us"] - plan["readout_delay_us"], 0)
        or not _vector(result["values"], n * 3, -50, 50)
        or not _modes(result["selected_modes"], n)
        or type(result["spike_counts"]) is not list
        or len(result["spike_counts"]) != n * 6
        or not all(_integer(item, 0, 1_000_000) for item in result["spike_counts"])
        or type(model) is not str
        or not 1 <= len(model) <= 64
        or len(model.encode("utf-8")) > 64
    ):
        _reject()
    for index, mode in enumerate(result["selected_modes"]):
        if (
            mode == "zero_acceleration"
            and any(
                value != 0 for value in result["values"][index * 3 : (index + 1) * 3]
            )
        ) or (not source["available"][index] and mode != "zero_acceleration"):
            _reject()


def validate_body_result(result: Any, plan: Any) -> None:
    """Check bounded application output; the supervisor must verify its source join."""
    _object(result, _BODY_KEYS)
    validate_snapshot(result["snapshot"], plan)
    n = len(plan["entity_ids"])
    if (
        result["schema"] != "ncp.local.body-result.v1"
        or result["plan_digest"] != plan_digest(plan)
        or not _integer(result["step"], 1, plan["planned_steps"])
        or result["step"] != result["snapshot"]["step"]
        or not valid_digest(result["source_snapshot_digest"])
        or not valid_digest(result["neural_result_digest"])
        or not _vector(result["proposed_values"], n * 3, -50, 50)
        or not _vector(result["applied_values"], n * 3, -50, 50)
        or not _booleans(result["saturated"], n)
        or not _modes(result["selected_modes"], n)
    ):
        _reject()
    for index, mode in enumerate(result["selected_modes"]):
        if mode == "zero_acceleration":
            if any(
                value != 0
                for name in ("proposed_values", "applied_values")
                for value in result[name][index * 3 : (index + 1) * 3]
            ):
                _reject()
