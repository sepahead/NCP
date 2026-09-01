#!/usr/bin/env python3
"""Report one non-authorizing B01 review handoff snapshot.

The report replays the exact current registry with the reviewer-kit-bound
generator. It does not write repository files, authenticate facts, or grant B01.
"""

from __future__ import annotations

# Disable bytecode before any import can resolve a repository module.
# ruff: noqa: E402, I001
import sys

sys.dont_write_bytecode = True

import argparse
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
from typing import Any, NoReturn

os.environ["GIT_NO_LAZY_FETCH"] = "1"
reviewer_kit = importlib.import_module("generate_b01_reviewer_kit")

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_RELATIVE = "scripts/check_b01_review_handoff.py"
STATUS_SCHEMA_RELATIVE = (
    "evidence/implementation/requests/B01/review-handoff-status.schema.v2.json"
)
STATUS_SCHEMA = "ncp.b01-review-handoff-status.v2"
STATUS_SCHEMA_ID = (
    "https://sepahead.github.io/NCP/schemas/b01-review-handoff-status.v2.json"
)
STATUS_CLAIM_BOUNDARY = (
    "CURRENT_STRUCTURAL_SNAPSHOT_ONLY_NO_AUTHENTICATED_REVIEWER_ROLE_"
    "AUTHORITY_INDEPENDENCE_APPEND_ONLY_HISTORY_HIGH_WATER_ADR_TASK_"
    "PROTOCOL_OR_RELEASE_AUTHORITY"
)

MAX_STATUS_SCHEMA_BYTES = 128 * 1024
MAX_STATUS_BYTES = 512 * 1024
EXPECTED_DECISION_COUNT = 11
EXPECTED_ROLE_OBLIGATION_COUNT = 52
EXPECTED_IDENTITY_SLOT_COUNT = 53
EXPECTED_INDEPENDENT_IDENTITY_SLOT_COUNT = 6
EXPECTED_DECISION_IDS = tuple(f"ADR-{number:03d}" for number in range(1, 12))
HEX_DIGITS = frozenset("0123456789abcdef")
EXPECTED_AUTHORITY = {
    "reviewer_identity_authentication": "NOT_EVALUATED",
    "role_authority": "NOT_EVALUATED",
    "independence": "NOT_EVALUATED",
    "append_only_history": "NOT_PROVED",
    "high_water_currentness": "NOT_PROVED",
    "b01": "NOT_GRANTED",
}
EXPECTED_INPUT_PATHS = {
    "status_schema": STATUS_SCHEMA_RELATIVE,
    "private_bundle_preflight": reviewer_kit.PREFLIGHT_RELATIVE,
    "bounded_json_reader": reviewer_kit.BOUNDED_JSON_RELATIVE,
    "schema_validator": reviewer_kit.SCHEMA_VALIDATOR_RELATIVE,
    "reviewer_kit": reviewer_kit.OUTPUT_RELATIVE,
    "reviewer_kit_generator": reviewer_kit.SCRIPT_RELATIVE,
    "review_request": reviewer_kit.REQUEST_RELATIVE,
    "review_request_generator": reviewer_kit.REQUEST_GENERATOR_RELATIVE,
    "immutable_git": reviewer_kit.IMMUTABLE_GIT_RELATIVE,
    "reviewer_kit_schema": reviewer_kit.KIT_SCHEMA_RELATIVE,
    "review_response_schema": reviewer_kit.RESPONSE_SCHEMA_RELATIVE,
    "review_source_candidate_schema": reviewer_kit.CANDIDATE_SCHEMA_RELATIVE,
    "registry_generator": reviewer_kit.REGISTRY_GENERATOR_RELATIVE,
    "registry_schema": reviewer_kit.REGISTRY_SCHEMA_RELATIVE,
    "registry_source": reviewer_kit.REGISTRY_SOURCE_RELATIVE,
    "proposed_registry": reviewer_kit.CURRENT_PROPOSED_REGISTRY_RELATIVE,
}


class ReviewHandoffError(RuntimeError):
    """The B01 handoff snapshot is incoherent or overclaims authority."""


def fail(message: str) -> NoReturn:
    raise ReviewHandoffError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def identity(relative: str, raw: bytes) -> dict[str, str | int]:
    return {"path": relative, "sha256": sha256(raw), "bytes": len(raw)}


def encoded(value: dict[str, Any]) -> bytes:
    try:
        raw = (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (RecursionError, TypeError, UnicodeError, ValueError) as error:
        raise ReviewHandoffError(
            f"cannot encode B01 handoff status: {error}"
        ) from error
    if not 1 <= len(raw) <= MAX_STATUS_BYTES:
        fail(f"B01 handoff status exceeds {MAX_STATUS_BYTES} bytes")
    return raw


def exact_keys(value: Any, expected: set[str], path: str) -> dict[str, Any]:
    if type(value) is not dict:
        fail(f"{path} must be one object")
    actual = set(value)
    if actual != expected:
        fail(
            f"{path} keys differ: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    return value


def snapshot_inputs() -> dict[str, bytes]:
    snapshots = reviewer_kit.snapshot_inputs()
    additional_limits = {
        SCRIPT_RELATIVE: reviewer_kit.MAX_SCRIPT_BYTES,
        STATUS_SCHEMA_RELATIVE: MAX_STATUS_SCHEMA_BYTES,
        reviewer_kit.OUTPUT_RELATIVE: reviewer_kit.MAX_KIT_BYTES,
        reviewer_kit.REGISTRY_SOURCE_RELATIVE: reviewer_kit.MAX_INPUT_BYTES,
        reviewer_kit.CURRENT_PROPOSED_REGISTRY_RELATIVE: reviewer_kit.MAX_INPUT_BYTES,
    }
    for relative, maximum in additional_limits.items():
        if relative in snapshots:
            fail(f"duplicate B01 handoff snapshot path: {relative}")
        snapshots[relative] = reviewer_kit.read_file(relative, maximum)
    source = reviewer_kit.parse_object(
        snapshots[reviewer_kit.REGISTRY_SOURCE_RELATIVE],
        reviewer_kit.REGISTRY_SOURCE_RELATIVE,
        reviewer_kit.MAX_INPUT_BYTES,
    )
    repository, evidence = reviewer_kit.snapshot_registry_replay_inputs(source)
    for relative, raw in {**repository, **evidence}.items():
        if relative in snapshots and snapshots[relative] != raw:
            fail("B01 handoff replay input differs across one snapshot")
        snapshots[relative] = raw
    return snapshots


def replay_maps(
    snapshots: dict[str, bytes], source: dict[str, Any]
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    repository = {
        relative: snapshots[relative]
        for relative in reviewer_kit.registry_replay_repository_paths(source)
    }
    evidence = {
        relative: snapshots[relative]
        for relative in reviewer_kit.registry_evidence_paths(source)
    }
    return repository, evidence


def current_snapshot() -> tuple[
    dict[str, Any],
    str,
    dict[str, bytes],
    dict[str, Any],
    dict[str, Any],
    list[dict[str, str | int]],
]:
    kit = reviewer_kit.build_kit()
    kit_bytes = reviewer_kit.generated_bytes(kit)
    reviewer_kit.require_retained_kit(kit, kit_bytes)
    validated_phase = reviewer_kit.validate_current_review_capture(kit)

    snapshots = snapshot_inputs()
    if snapshots[reviewer_kit.OUTPUT_RELATIVE] != kit_bytes:
        fail("retained reviewer kit changed between lifecycle and status checks")
    if kit["generated_by"] != identity(
        reviewer_kit.SCRIPT_RELATIVE,
        snapshots[reviewer_kit.SCRIPT_RELATIVE],
    ):
        fail("reviewer-kit generator differs from the retained reviewer kit")
    for input_name, relative in (
        ("private_bundle_preflight", reviewer_kit.PREFLIGHT_RELATIVE),
        ("bounded_json_reader", reviewer_kit.BOUNDED_JSON_RELATIVE),
        ("immutable_git_reader", reviewer_kit.IMMUTABLE_GIT_RELATIVE),
        ("schema_validator", reviewer_kit.SCHEMA_VALIDATOR_RELATIVE),
        ("review_request", reviewer_kit.REQUEST_RELATIVE),
        ("reviewer_kit_schema", reviewer_kit.KIT_SCHEMA_RELATIVE),
        ("review_response_schema", reviewer_kit.RESPONSE_SCHEMA_RELATIVE),
        (
            "review_source_candidate_schema",
            reviewer_kit.CANDIDATE_SCHEMA_RELATIVE,
        ),
        ("decision_registry_generator", reviewer_kit.REGISTRY_GENERATOR_RELATIVE),
        ("decision_registry_schema", reviewer_kit.REGISTRY_SCHEMA_RELATIVE),
    ):
        if kit["inputs"][input_name] != identity(relative, snapshots[relative]):
            fail(f"status input {relative} differs from the retained reviewer kit")
    if kit["subject_cut"]["review_packet"] != identity(
        reviewer_kit.REVIEW_PACKET_RELATIVE,
        snapshots[reviewer_kit.REVIEW_PACKET_RELATIVE],
    ):
        fail("current review packet differs from the retained reviewer kit")

    source = reviewer_kit.parse_object(
        snapshots[reviewer_kit.REGISTRY_SOURCE_RELATIVE],
        reviewer_kit.REGISTRY_SOURCE_RELATIVE,
        reviewer_kit.MAX_INPUT_BYTES,
    )
    repository_snapshots, evidence_snapshots = replay_maps(snapshots, source)
    generated, serialized = reviewer_kit.execute_exact_registry_generator(
        snapshots[reviewer_kit.REGISTRY_GENERATOR_RELATIVE],
        source,
        artifact_overrides=evidence_snapshots,
        immutable_git_source=snapshots[reviewer_kit.IMMUTABLE_GIT_RELATIVE],
        bounded_json_source=snapshots[reviewer_kit.BOUNDED_JSON_RELATIVE],
        schema_validator_source=snapshots[reviewer_kit.SCHEMA_VALIDATOR_RELATIVE],
        repository_snapshots=repository_snapshots,
    )
    if serialized != snapshots[reviewer_kit.CURRENT_PROPOSED_REGISTRY_RELATIVE]:
        fail("current proposed registry differs from its exact source replay")
    observed_phase = reviewer_kit.review_capture_phase_value(source, generated)
    if observed_phase != validated_phase:
        fail("B01 review phase changed between lifecycle and status checks")
    if snapshot_inputs() != snapshots:
        fail("B01 handoff inputs changed while the status snapshot was built")
    final_generated, final_serialized = reviewer_kit.execute_exact_registry_generator(
        snapshots[reviewer_kit.REGISTRY_GENERATOR_RELATIVE],
        source,
        artifact_overrides=evidence_snapshots,
        immutable_git_source=snapshots[reviewer_kit.IMMUTABLE_GIT_RELATIVE],
        bounded_json_source=snapshots[reviewer_kit.BOUNDED_JSON_RELATIVE],
        schema_validator_source=snapshots[reviewer_kit.SCHEMA_VALIDATOR_RELATIVE],
        repository_snapshots=repository_snapshots,
    )
    if (
        final_serialized != snapshots[reviewer_kit.CURRENT_PROPOSED_REGISTRY_RELATIVE]
        or final_generated != generated
    ):
        fail("transitive registry inputs changed during the handoff snapshot")
    if snapshot_inputs() != snapshots:
        fail("B01 handoff inputs changed during the final transitive replay")
    replay_inputs = reviewer_kit.registry_replay_input_identities(
        repository_snapshots,
        evidence_snapshots,
    )
    return kit, observed_phase, snapshots, source, generated, replay_inputs


def _qualifying_identities(
    records: list[dict[str, Any]], adr_id: str, role_id: str
) -> list[str]:
    identities: list[str] = []
    observed: set[str] = set()
    for record in records:
        derived = record.get("derived")
        reviewer = record.get("reviewer")
        if (
            record.get("adr_id") != adr_id
            or record.get("role_id") != role_id
            or type(derived) is not dict
            or derived.get("qualifying_acceptance") is not True
            or type(reviewer) is not dict
            or type(reviewer.get("identity")) is not str
        ):
            continue
        reviewer_identity = reviewer["identity"]
        if reviewer_identity not in observed:
            observed.add(reviewer_identity)
            identities.append(reviewer_identity)
    return identities


def build_status(
    kit: dict[str, Any],
    phase: str,
    snapshots: dict[str, bytes],
    source: dict[str, Any],
    generated: dict[str, Any],
    registry_replay_inputs: list[dict[str, str | int]],
) -> dict[str, Any]:
    reviewer_kit.validate_registry_replay_identities(registry_replay_inputs)
    records = generated.get("review_records")
    decisions = generated.get("decisions")
    if type(records) is not list or type(decisions) is not list:
        fail("generated registry lacks bounded decisions or review records")
    if len(records) > reviewer_kit.MAX_REVIEW_RECORDS:
        fail("generated registry exceeds the review-record bound")
    if len(decisions) != EXPECTED_DECISION_COUNT:
        fail("generated registry does not contain exactly eleven decisions")
    if phase == reviewer_kit.ZERO_REVIEW_ISSUANCE and records:
        fail("zero-review phase contains review records")
    if phase == reviewer_kit.REVIEW_CAPTURE_ACTIVE and not records:
        fail("active review phase contains no review records")

    decision_rows: list[dict[str, Any]] = []
    role_obligations_satisfied = 0
    role_obligations_total = 0
    identity_slots_satisfied = 0
    identity_slots_total = 0
    independent_identity_slots_satisfied = 0
    independent_identity_slots_total = 0
    observed_decision_ids: list[str] = []

    for decision in decisions:
        decision = exact_keys(
            decision,
            {
                "id",
                "title",
                "path",
                "module_paths",
                "content_sha256",
                "bytes",
                "source_set",
                "required_reviews",
                "defect_ids",
                "status",
                "acceptance_blockers",
            },
            "generated decision",
        )
        adr_id = decision["id"]
        if type(adr_id) is not str:
            fail("generated decision ID must be text")
        observed_decision_ids.append(adr_id)
        blockers = decision["acceptance_blockers"]
        requirements = decision["required_reviews"]
        if type(blockers) is not list or type(requirements) is not list:
            fail(f"{adr_id} lacks bounded blockers or review requirements")
        if (decision["status"] == "ACCEPTED") != (not blockers):
            fail(f"{adr_id} status differs from its exact blocker set")
        if decision["status"] not in {"PROPOSED", "ACCEPTED"}:
            fail(f"{adr_id} has an unknown decision status")

        blocker_codes: list[str] = []
        for blocker in blockers:
            if type(blocker) is not dict or type(blocker.get("code")) is not str:
                fail(f"{adr_id} contains a malformed blocker")
            code = blocker["code"]
            if code not in blocker_codes:
                blocker_codes.append(code)

        role_rows: list[dict[str, Any]] = []
        for requirement in requirements:
            requirement = exact_keys(
                requirement,
                {
                    "role_id",
                    "label",
                    "min_distinct_identities",
                    "requires_independence",
                },
                f"{adr_id} review requirement",
            )
            role_id = requirement["role_id"]
            minimum = requirement["min_distinct_identities"]
            requires_independence = requirement["requires_independence"]
            if (
                type(role_id) is not str
                or type(minimum) is not int
                or not 1 <= minimum <= 32
                or type(requires_independence) is not bool
            ):
                fail(f"{adr_id} has a malformed review requirement")
            role_obligations_total += 1
            identity_slots_total += minimum
            if requires_independence:
                independent_identity_slots_total += minimum

            identities = _qualifying_identities(records, adr_id, role_id)
            observed = len(identities)
            shortage = max(0, minimum - observed)
            missing_role_blockers = [
                blocker
                for blocker in blockers
                if blocker.get("code") == "MISSING_ROLE_ACCEPTANCE"
                and blocker.get("role_id") == role_id
            ]
            if (shortage > 0) != (len(missing_role_blockers) == 1):
                fail(f"{adr_id}/{role_id} shortage differs from registry blockers")

            slots = sorted(
                (
                    slot
                    for slot in kit["slots"]
                    if slot["adr_id"] == adr_id and slot["role_id"] == role_id
                ),
                key=lambda slot: slot["identity_ordinal"],
            )
            if (
                len(slots) != minimum
                or [slot["identity_ordinal"] for slot in slots]
                != list(range(1, minimum + 1))
                or any(
                    slot["requires_independence"] != requires_independence
                    for slot in slots
                )
            ):
                fail(f"{adr_id}/{role_id} slot allocation differs from its requirement")
            suggested_next_slot_id = (
                slots[min(observed, minimum - 1)]["slot_id"] if shortage else None
            )
            satisfied_slots = min(observed, minimum)
            identity_slots_satisfied += satisfied_slots
            if requires_independence:
                independent_identity_slots_satisfied += satisfied_slots
            if not shortage:
                role_obligations_satisfied += 1
            role_rows.append(
                {
                    "role_id": role_id,
                    "label": requirement["label"],
                    "requires_independence": requires_independence,
                    "minimum_distinct_identities": minimum,
                    "structurally_qualifying_identity_count": observed,
                    "minimum_identity_shortage": shortage,
                    "suggested_next_slot_id": suggested_next_slot_id,
                }
            )

        decision_rows.append(
            {
                "adr_id": adr_id,
                "title": decision["title"],
                "status": decision["status"],
                "blocker_codes": blocker_codes,
                "roles": role_rows,
            }
        )

    if tuple(observed_decision_ids) != EXPECTED_DECISION_IDS:
        fail("generated decision ordering differs from ADR-001 through ADR-011")
    if role_obligations_total != EXPECTED_ROLE_OBLIGATION_COUNT:
        fail("generated role-obligation count differs from 52")
    if identity_slots_total != EXPECTED_IDENTITY_SLOT_COUNT:
        fail("generated identity-slot count differs from 53")
    if independent_identity_slots_total != (EXPECTED_INDEPENDENT_IDENTITY_SLOT_COUNT):
        fail("generated independent identity-slot count differs from 6")

    active_records = 0
    current_subject_records = 0
    qualifying_records = 0
    active_rejections = 0
    active_open_conditions = 0
    for index, record in enumerate(records):
        if type(record) is not dict:
            fail(f"generated review record {index} must be one object")
        derived = record.get("derived")
        conditions = record.get("conditions")
        if type(derived) is not dict or type(conditions) is not list:
            fail(f"generated review record {index} lacks derived state or conditions")
        active = derived.get("active")
        current_subject = derived.get("current_subject")
        qualifying = derived.get("qualifying_acceptance")
        if any(
            type(value) is not bool for value in (active, current_subject, qualifying)
        ):
            fail(f"generated review record {index} has malformed derived flags")
        active_records += int(active)
        current_subject_records += int(current_subject)
        qualifying_records += int(qualifying)
        active_rejections += int(active and record.get("decision") == "REJECT")
        active_open_conditions += sum(
            1
            for condition in conditions
            if active and type(condition) is dict and condition.get("status") == "OPEN"
        )

    subject_cut = kit["subject_cut"]
    status_inputs = {
        name: identity(relative, snapshots[relative])
        for name, relative in EXPECTED_INPUT_PATHS.items()
    }
    status_inputs["registry_replay_inputs"] = copy.deepcopy(registry_replay_inputs)
    status = {
        "schema": STATUS_SCHEMA,
        "normative": False,
        "authorizing": False,
        "registry_mutation": False,
        "snapshot_only": True,
        "external_verifier_required": True,
        "history_assurance": "NOT_ESTABLISHED",
        "review_authentication": "NOT_ESTABLISHED",
        "claim_boundary": STATUS_CLAIM_BOUNDARY,
        "phase": phase,
        "generated_by": identity(SCRIPT_RELATIVE, snapshots[SCRIPT_RELATIVE]),
        "subject": {
            "decision_set_sha256": subject_cut["decision_set_sha256"],
            "review_packet": copy.deepcopy(subject_cut["review_packet"]),
            "zero_review_source_commit": subject_cut["zero_review_source_commit"],
            "zero_review_source_tree": subject_cut["zero_review_source_tree"],
        },
        "inputs": status_inputs,
        "counts": {
            "decisions_total": EXPECTED_DECISION_COUNT,
            "decisions_accepted": sum(
                row["status"] == "ACCEPTED" for row in decision_rows
            ),
            "role_obligations_total": role_obligations_total,
            "role_obligations_structurally_satisfied": role_obligations_satisfied,
            "identity_slots_total": identity_slots_total,
            "identity_slots_structurally_satisfied": identity_slots_satisfied,
            "independent_identity_slots_total": (independent_identity_slots_total),
            "independent_identity_slots_structurally_satisfied": (
                independent_identity_slots_satisfied
            ),
            "review_records_total": len(records),
            "active_review_records": active_records,
            "superseded_review_records": len(records) - active_records,
            "current_subject_review_records": current_subject_records,
            "stale_review_records": len(records) - current_subject_records,
            "structurally_qualifying_review_records": qualifying_records,
            "active_rejections": active_rejections,
            "active_open_conditions": active_open_conditions,
        },
        "decisions": decision_rows,
        "authority": copy.deepcopy(EXPECTED_AUTHORITY),
    }
    if source.get("review_records") is None or len(source["review_records"]) != len(
        records
    ):
        fail("registry source and generated review-record counts differ")
    return status


def require_hex(value: Any, length: int, path: str) -> str:
    if (
        type(value) is not str
        or len(value) != length
        or any(character not in HEX_DIGITS for character in value)
    ):
        fail(f"{path} must be one canonical lowercase hexadecimal value")
    return value


def validate_file_identity(value: Any, expected_path: str, path: str) -> None:
    value = exact_keys(value, {"path", "sha256", "bytes"}, path)
    if value["path"] != expected_path:
        fail(f"{path}.path must equal {expected_path}")
    require_hex(value["sha256"], 64, f"{path}.sha256")
    byte_count = value["bytes"]
    if type(byte_count) is not int or not 1 <= byte_count <= 4 * 1024 * 1024:
        fail(f"{path}.bytes must be an integer from 1 through 4194304")


def validate_status_semantics(
    status: dict[str, Any],
    snapshots: dict[str, bytes],
    subject_cut: dict[str, Any],
    registry_replay_inputs: list[dict[str, str | int]],
) -> None:
    exact_keys(
        status,
        {
            "schema",
            "normative",
            "authorizing",
            "registry_mutation",
            "snapshot_only",
            "external_verifier_required",
            "history_assurance",
            "review_authentication",
            "claim_boundary",
            "phase",
            "generated_by",
            "subject",
            "inputs",
            "counts",
            "decisions",
            "authority",
        },
        "B01 review handoff status",
    )
    if (
        status["schema"] != STATUS_SCHEMA
        or status["normative"] is not False
        or status["authorizing"] is not False
        or status["registry_mutation"] is not False
        or status["snapshot_only"] is not True
        or status["external_verifier_required"] is not True
        or status["history_assurance"] != "NOT_ESTABLISHED"
        or status["review_authentication"] != "NOT_ESTABLISHED"
        or status["claim_boundary"] != STATUS_CLAIM_BOUNDARY
    ):
        fail("B01 review handoff status changed its non-authorizing boundary")
    if status["phase"] not in {
        reviewer_kit.ZERO_REVIEW_ISSUANCE,
        reviewer_kit.REVIEW_CAPTURE_ACTIVE,
    }:
        fail("B01 review handoff status has an unknown phase")

    validate_file_identity(
        status["generated_by"],
        SCRIPT_RELATIVE,
        "B01 review handoff status.generated_by",
    )
    if status["generated_by"] != identity(SCRIPT_RELATIVE, snapshots[SCRIPT_RELATIVE]):
        fail("status generator identity differs from the captured bytes")
    subject = exact_keys(
        status["subject"],
        {
            "decision_set_sha256",
            "review_packet",
            "zero_review_source_commit",
            "zero_review_source_tree",
        },
        "B01 review handoff status.subject",
    )
    require_hex(
        subject["decision_set_sha256"],
        64,
        "B01 review handoff status.subject.decision_set_sha256",
    )
    validate_file_identity(
        subject["review_packet"],
        reviewer_kit.REVIEW_PACKET_RELATIVE,
        "B01 review handoff status.subject.review_packet",
    )
    require_hex(
        subject["zero_review_source_commit"],
        40,
        "B01 review handoff status.subject.zero_review_source_commit",
    )
    require_hex(
        subject["zero_review_source_tree"],
        40,
        "B01 review handoff status.subject.zero_review_source_tree",
    )
    expected_subject = {
        "decision_set_sha256": subject_cut["decision_set_sha256"],
        "review_packet": identity(
            reviewer_kit.REVIEW_PACKET_RELATIVE,
            snapshots[reviewer_kit.REVIEW_PACKET_RELATIVE],
        ),
        "zero_review_source_commit": subject_cut["zero_review_source_commit"],
        "zero_review_source_tree": subject_cut["zero_review_source_tree"],
    }
    if subject != expected_subject:
        fail("status subject differs from the retained captured subject")

    inputs = exact_keys(
        status["inputs"],
        set(EXPECTED_INPUT_PATHS) | {"registry_replay_inputs"},
        "B01 review handoff status.inputs",
    )
    for name, expected_path in EXPECTED_INPUT_PATHS.items():
        validate_file_identity(
            inputs[name],
            expected_path,
            f"B01 review handoff status.inputs.{name}",
        )
        if inputs[name] != identity(expected_path, snapshots[expected_path]):
            fail(f"status input {name} differs from the captured bytes")
    reviewer_kit.validate_registry_replay_identities(inputs["registry_replay_inputs"])
    reviewer_kit.validate_registry_replay_identities(registry_replay_inputs)
    if inputs["registry_replay_inputs"] != registry_replay_inputs:
        fail("status registry replay inputs differ from the captured byte roster")

    decisions = status["decisions"]
    if type(decisions) is not list or len(decisions) != EXPECTED_DECISION_COUNT:
        fail("B01 review handoff status must contain exactly eleven decisions")
    observed_decision_ids: list[str] = []
    decisions_accepted = 0
    role_obligations_total = 0
    role_obligations_satisfied = 0
    identity_slots_total = 0
    identity_slots_satisfied = 0
    independent_identity_slots_total = 0
    independent_identity_slots_satisfied = 0
    for decision_index, decision in enumerate(decisions):
        decision = exact_keys(
            decision,
            {"adr_id", "title", "status", "blocker_codes", "roles"},
            f"B01 review handoff status.decisions[{decision_index}]",
        )
        adr_id = decision["adr_id"]
        if type(adr_id) is not str:
            fail(f"status decision {decision_index} has a non-text ADR ID")
        observed_decision_ids.append(adr_id)
        if type(decision["title"]) is not str or not decision["title"]:
            fail(f"{adr_id} has an empty or non-text title")
        blocker_codes = decision["blocker_codes"]
        if (
            type(blocker_codes) is not list
            or len(blocker_codes) > 64
            or len(blocker_codes) != len(set(blocker_codes))
            or any(
                type(code) is not str or not code or len(code) > 64
                for code in blocker_codes
            )
        ):
            fail(f"{adr_id} has malformed or duplicate blocker codes")
        decision_status = decision["status"]
        if decision_status not in {"PROPOSED", "ACCEPTED"}:
            fail(f"{adr_id} has an unknown decision status")
        if (decision_status == "ACCEPTED") != (not blocker_codes):
            fail(f"{adr_id} status differs from its blocker-code set")
        decisions_accepted += int(decision_status == "ACCEPTED")

        roles = decision["roles"]
        if type(roles) is not list or not 1 <= len(roles) <= 16:
            fail(f"{adr_id} has an invalid role roster")
        observed_role_ids: set[str] = set()
        decision_has_shortage = False
        for role_index, role in enumerate(roles):
            role = exact_keys(
                role,
                {
                    "role_id",
                    "label",
                    "requires_independence",
                    "minimum_distinct_identities",
                    "structurally_qualifying_identity_count",
                    "minimum_identity_shortage",
                    "suggested_next_slot_id",
                },
                f"{adr_id}.roles[{role_index}]",
            )
            role_id = role["role_id"]
            if (
                type(role_id) is not str
                or not 1 <= len(role_id) <= 64
                or any(
                    not part
                    or any(
                        character not in "abcdefghijklmnopqrstuvwxyz0123456789"
                        for character in part
                    )
                    for part in role_id.split("-")
                )
                or role_id in observed_role_ids
            ):
                fail(f"{adr_id} has a malformed or duplicate role ID")
            observed_role_ids.add(role_id)
            if type(role["label"]) is not str or not role["label"]:
                fail(f"{adr_id}/{role_id} has an empty or non-text label")
            requires_independence = role["requires_independence"]
            minimum = role["minimum_distinct_identities"]
            observed = role["structurally_qualifying_identity_count"]
            shortage = role["minimum_identity_shortage"]
            if type(requires_independence) is not bool:
                fail(f"{adr_id}/{role_id} has a malformed independence flag")
            if type(minimum) is not int or not 1 <= minimum <= 32:
                fail(f"{adr_id}/{role_id} has an invalid identity minimum")
            if (
                type(observed) is not int
                or not 0 <= observed <= reviewer_kit.MAX_REVIEW_RECORDS
            ):
                fail(f"{adr_id}/{role_id} has an invalid observed identity count")
            expected_shortage = max(0, minimum - observed)
            if type(shortage) is not int or shortage != expected_shortage:
                fail(f"{adr_id}/{role_id} has an incoherent identity shortage")
            expected_suggested_next_slot = (
                f"{adr_id.lower()}.{role_id}.{observed + 1:02d}" if shortage else None
            )
            if role["suggested_next_slot_id"] != expected_suggested_next_slot:
                fail(f"{adr_id}/{role_id} has an incoherent suggested slot")

            role_obligations_total += 1
            identity_slots_total += minimum
            satisfied_slots = min(observed, minimum)
            identity_slots_satisfied += satisfied_slots
            if requires_independence:
                independent_identity_slots_total += minimum
                independent_identity_slots_satisfied += satisfied_slots
            if shortage:
                decision_has_shortage = True
            else:
                role_obligations_satisfied += 1
        if decision_has_shortage != ("MISSING_ROLE_ACCEPTANCE" in blocker_codes):
            fail(f"{adr_id} role shortages differ from its blocker-code set")

    if tuple(observed_decision_ids) != EXPECTED_DECISION_IDS:
        fail("status decision ordering differs from ADR-001 through ADR-011")

    counts = exact_keys(
        status["counts"],
        {
            "decisions_total",
            "decisions_accepted",
            "role_obligations_total",
            "role_obligations_structurally_satisfied",
            "identity_slots_total",
            "identity_slots_structurally_satisfied",
            "independent_identity_slots_total",
            "independent_identity_slots_structurally_satisfied",
            "review_records_total",
            "active_review_records",
            "superseded_review_records",
            "current_subject_review_records",
            "stale_review_records",
            "structurally_qualifying_review_records",
            "active_rejections",
            "active_open_conditions",
        },
        "B01 review handoff status.counts",
    )
    expected_counts = {
        "decisions_total": len(decisions),
        "decisions_accepted": decisions_accepted,
        "role_obligations_total": role_obligations_total,
        "role_obligations_structurally_satisfied": role_obligations_satisfied,
        "identity_slots_total": identity_slots_total,
        "identity_slots_structurally_satisfied": identity_slots_satisfied,
        "independent_identity_slots_total": independent_identity_slots_total,
        "independent_identity_slots_structurally_satisfied": (
            independent_identity_slots_satisfied
        ),
    }
    for name, expected in expected_counts.items():
        if type(counts[name]) is not int or counts[name] != expected:
            fail(f"status count {name} differs from the decision projection")
    record_count_names = (
        "review_records_total",
        "active_review_records",
        "superseded_review_records",
        "current_subject_review_records",
        "stale_review_records",
        "structurally_qualifying_review_records",
        "active_rejections",
    )
    for name in record_count_names:
        if (
            type(counts[name]) is not int
            or not 0 <= counts[name] <= reviewer_kit.MAX_REVIEW_RECORDS
        ):
            fail(f"status count {name} is outside the review-record bound")
    open_conditions = counts["active_open_conditions"]
    if type(open_conditions) is not int or not 0 <= open_conditions <= 4096:
        fail("status active-open-condition count is outside its bound")
    total_records = counts["review_records_total"]
    active_records = counts["active_review_records"]
    current_records = counts["current_subject_review_records"]
    qualifying_records = counts["structurally_qualifying_review_records"]
    if counts["superseded_review_records"] != total_records - active_records:
        fail("status active and superseded review counts are incoherent")
    if counts["stale_review_records"] != total_records - current_records:
        fail("status current and stale review counts are incoherent")
    if qualifying_records > min(active_records, current_records):
        fail("status qualifying review count exceeds active current reviews")
    if counts["active_rejections"] > active_records:
        fail("status active rejection count exceeds active reviews")
    if qualifying_records + counts["active_rejections"] > active_records:
        fail("status qualifying acceptances and active rejections overlap")
    if open_conditions > active_records * 16:
        fail("status open-condition count exceeds active review capacity")
    if status["phase"] == reviewer_kit.ZERO_REVIEW_ISSUANCE and total_records:
        fail("zero-review status contains review records")
    if status["phase"] == reviewer_kit.REVIEW_CAPTURE_ACTIVE and not total_records:
        fail("active-review status contains no review records")
    if status["authority"] != EXPECTED_AUTHORITY:
        fail("B01 review handoff status changed its authority non-claims")


def validate_status(
    status: dict[str, Any],
    schema_raw: bytes,
    snapshots: dict[str, bytes],
    subject_cut: dict[str, Any],
    registry_replay_inputs: list[dict[str, str | int]],
) -> None:
    schema = reviewer_kit.parse_object(
        schema_raw,
        STATUS_SCHEMA_RELATIVE,
        MAX_STATUS_SCHEMA_BYTES,
    )
    reviewer_kit.schema_validate(
        schema,
        status,
        "B01 review handoff status",
        STATUS_SCHEMA_ID,
    )
    validate_status_semantics(
        status,
        snapshots,
        subject_cut,
        registry_replay_inputs,
    )
    encoded(status)


def build_current_status() -> dict[str, Any]:
    kit, phase, snapshots, source, generated, replay_inputs = current_snapshot()
    status = build_status(kit, phase, snapshots, source, generated, replay_inputs)
    validate_status(
        status,
        snapshots[STATUS_SCHEMA_RELATIVE],
        snapshots,
        kit["subject_cut"],
        replay_inputs,
    )
    if snapshot_inputs() != snapshots:
        fail("B01 handoff inputs changed during final status validation")
    return status


def must_fail(action: Any, label: str) -> None:
    try:
        action()
    except (ReviewHandoffError, reviewer_kit.ReviewerKitError):
        return
    fail(f"hostile B01 handoff self-test unexpectedly passed: {label}")


def synthetic_record(
    adr_id: str,
    role_id: str,
    ordinal: int,
    *,
    identity_ordinal: int | None = None,
    active: bool = True,
    current_subject: bool = True,
    qualifying: bool = True,
    decision: str = "ACCEPT",
    open_condition: bool = False,
) -> dict[str, Any]:
    identity_number = ordinal if identity_ordinal is None else identity_ordinal
    return {
        "review_id": f"self-test-review-{ordinal:03d}",
        "adr_id": adr_id,
        "role_id": role_id,
        "reviewer": {"identity": f"urn:ncp:self-test-reviewer:{identity_number:03d}"},
        "decision": decision,
        "conditions": ([{"status": "OPEN"}] if open_condition else []),
        "derived": {
            "active": active,
            "current_subject": current_subject,
            "qualifying_acceptance": qualifying,
        },
    }


def projected_active_status(
    kit: dict[str, Any],
    snapshots: dict[str, bytes],
    source: dict[str, Any],
    generated: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    satisfied_role: tuple[str, str] | None,
) -> dict[str, Any]:
    repository_snapshots, evidence_snapshots = replay_maps(snapshots, source)
    registry_replay_inputs = reviewer_kit.registry_replay_input_identities(
        repository_snapshots,
        evidence_snapshots,
    )
    active_source = copy.deepcopy(source)
    active_source["review_records"] = copy.deepcopy(records)
    active_generated = copy.deepcopy(generated)
    active_generated["review_records"] = copy.deepcopy(records)
    if satisfied_role is not None:
        adr_id, role_id = satisfied_role
        decision = next(
            row for row in active_generated["decisions"] if row["id"] == adr_id
        )
        decision["acceptance_blockers"] = [
            blocker
            for blocker in decision["acceptance_blockers"]
            if not (
                blocker.get("code") == "MISSING_ROLE_ACCEPTANCE"
                and blocker.get("role_id") == role_id
            )
        ]
    projection_snapshots = dict(snapshots)
    projection_snapshots[reviewer_kit.REGISTRY_SOURCE_RELATIVE] = (
        json.dumps(
            active_source,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    projection_snapshots[reviewer_kit.CURRENT_PROPOSED_REGISTRY_RELATIVE] = (
        reviewer_kit.generated_bytes(active_generated)
    )
    projected = build_status(
        kit,
        reviewer_kit.REVIEW_CAPTURE_ACTIVE,
        projection_snapshots,
        active_source,
        active_generated,
        registry_replay_inputs,
    )
    validate_status(
        projected,
        projection_snapshots[STATUS_SCHEMA_RELATIVE],
        projection_snapshots,
        kit["subject_cut"],
        registry_replay_inputs,
    )
    return projected


def self_test() -> None:
    if not sys.dont_write_bytecode or os.environ.get("GIT_NO_LAZY_FETCH") != "1":
        fail("B01 handoff runtime lost its no-bytecode or no-lazy-fetch guard")
    kit, phase, snapshots, source, generated, replay_inputs = current_snapshot()
    status = build_status(kit, phase, snapshots, source, generated, replay_inputs)
    validate_status(
        status,
        snapshots[STATUS_SCHEMA_RELATIVE],
        snapshots,
        kit["subject_cut"],
        replay_inputs,
    )
    if encoded(status) != encoded(
        build_status(kit, phase, snapshots, source, generated, replay_inputs)
    ):
        fail("B01 handoff status is not deterministic")

    projection_source = copy.deepcopy(source)
    projection_source["review_records"] = []
    projection_repository, projection_evidence = replay_maps(
        snapshots,
        projection_source,
    )
    projection_generated, projection_serialized = (
        reviewer_kit.execute_exact_registry_generator(
            snapshots[reviewer_kit.REGISTRY_GENERATOR_RELATIVE],
            projection_source,
            artifact_overrides=projection_evidence,
            immutable_git_source=snapshots[reviewer_kit.IMMUTABLE_GIT_RELATIVE],
            bounded_json_source=snapshots[reviewer_kit.BOUNDED_JSON_RELATIVE],
            schema_validator_source=snapshots[reviewer_kit.SCHEMA_VALIDATOR_RELATIVE],
            repository_snapshots=projection_repository,
        )
    )
    projection_replay_inputs = reviewer_kit.registry_replay_input_identities(
        projection_repository,
        projection_evidence,
    )
    if (
        reviewer_kit.review_capture_phase_value(projection_source, projection_generated)
        != reviewer_kit.ZERO_REVIEW_ISSUANCE
    ):
        fail("isolated self-test source is not a zero-review projection")
    projection_snapshots = dict(snapshots)
    projection_snapshots[reviewer_kit.REGISTRY_SOURCE_RELATIVE] = (
        json.dumps(
            projection_source,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    projection_snapshots[reviewer_kit.CURRENT_PROPOSED_REGISTRY_RELATIVE] = (
        projection_serialized
    )
    projection_status = build_status(
        kit,
        reviewer_kit.ZERO_REVIEW_ISSUANCE,
        projection_snapshots,
        projection_source,
        projection_generated,
        projection_replay_inputs,
    )
    validate_status(
        projection_status,
        projection_snapshots[STATUS_SCHEMA_RELATIVE],
        projection_snapshots,
        kit["subject_cut"],
        projection_replay_inputs,
    )

    counts = projection_status["counts"]
    if counts != {
        "decisions_total": 11,
        "decisions_accepted": 0,
        "role_obligations_total": 52,
        "role_obligations_structurally_satisfied": 0,
        "identity_slots_total": 53,
        "identity_slots_structurally_satisfied": 0,
        "independent_identity_slots_total": 6,
        "independent_identity_slots_structurally_satisfied": 0,
        "review_records_total": 0,
        "active_review_records": 0,
        "superseded_review_records": 0,
        "current_subject_review_records": 0,
        "stale_review_records": 0,
        "structurally_qualifying_review_records": 0,
        "active_rejections": 0,
        "active_open_conditions": 0,
    }:
        fail("zero-review handoff status changed its exact counts")

    one_of_two = synthetic_record("ADR-003", "security-cryptography-reviewer", 1)
    one_of_two_status = projected_active_status(
        kit,
        projection_snapshots,
        projection_source,
        projection_generated,
        [one_of_two],
        satisfied_role=None,
    )
    one_of_two_role = next(
        role
        for decision in one_of_two_status["decisions"]
        if decision["adr_id"] == "ADR-003"
        for role in decision["roles"]
        if role["role_id"] == "security-cryptography-reviewer"
    )
    if (
        one_of_two_role["structurally_qualifying_identity_count"] != 1
        or one_of_two_role["minimum_identity_shortage"] != 1
        or one_of_two_role["suggested_next_slot_id"]
        != "adr-003.security-cryptography-reviewer.02"
    ):
        fail("one-of-two active review projection changed its shortage")

    two_of_two = [
        one_of_two,
        synthetic_record("ADR-003", "security-cryptography-reviewer", 2),
    ]
    two_of_two_status = projected_active_status(
        kit,
        projection_snapshots,
        projection_source,
        projection_generated,
        two_of_two,
        satisfied_role=("ADR-003", "security-cryptography-reviewer"),
    )
    two_of_two_role = next(
        role
        for decision in two_of_two_status["decisions"]
        if decision["adr_id"] == "ADR-003"
        for role in decision["roles"]
        if role["role_id"] == "security-cryptography-reviewer"
    )
    if (
        two_of_two_role["structurally_qualifying_identity_count"] != 2
        or two_of_two_role["minimum_identity_shortage"] != 0
        or two_of_two_role["suggested_next_slot_id"] is not None
    ):
        fail("two-of-two active review projection did not satisfy its role")

    duplicate_identity = [
        one_of_two,
        synthetic_record(
            "ADR-003",
            "security-cryptography-reviewer",
            2,
            identity_ordinal=1,
        ),
    ]
    duplicate_identity_status = projected_active_status(
        kit,
        projection_snapshots,
        projection_source,
        projection_generated,
        duplicate_identity,
        satisfied_role=None,
    )
    duplicate_identity_role = next(
        role
        for decision in duplicate_identity_status["decisions"]
        if decision["adr_id"] == "ADR-003"
        for role in decision["roles"]
        if role["role_id"] == "security-cryptography-reviewer"
    )
    if duplicate_identity_role["structurally_qualifying_identity_count"] != 1:
        fail("duplicate reviewer identity satisfied two identity slots")

    thirty_three_records = [
        synthetic_record("ADR-001", "ncp-maintainer", ordinal)
        for ordinal in range(1, 34)
    ]
    thirty_three_status = projected_active_status(
        kit,
        projection_snapshots,
        projection_source,
        projection_generated,
        thirty_three_records,
        satisfied_role=("ADR-001", "ncp-maintainer"),
    )
    thirty_three_role = thirty_three_status["decisions"][0]["roles"][0]
    if (
        thirty_three_role["structurally_qualifying_identity_count"] != 33
        or thirty_three_role["minimum_identity_shortage"] != 0
        or thirty_three_role["suggested_next_slot_id"] is not None
    ):
        fail("surplus active reviewer projection changed or failed")

    mixed_records = [
        synthetic_record("ADR-001", "ncp-maintainer", 1),
        synthetic_record(
            "ADR-001",
            "ncp-maintainer",
            2,
            active=False,
            current_subject=False,
            qualifying=False,
        ),
        synthetic_record(
            "ADR-001",
            "ncp-maintainer",
            3,
            qualifying=False,
            decision="REJECT",
        ),
        synthetic_record(
            "ADR-001",
            "ncp-maintainer",
            4,
            qualifying=False,
            open_condition=True,
        ),
    ]
    mixed_status = projected_active_status(
        kit,
        projection_snapshots,
        projection_source,
        projection_generated,
        mixed_records,
        satisfied_role=("ADR-001", "ncp-maintainer"),
    )
    if any(
        mixed_status["counts"][name] != expected
        for name, expected in {
            "review_records_total": 4,
            "active_review_records": 3,
            "superseded_review_records": 1,
            "current_subject_review_records": 3,
            "stale_review_records": 1,
            "structurally_qualifying_review_records": 1,
            "active_rejections": 1,
            "active_open_conditions": 1,
        }.items()
    ):
        fail("mixed active review projection changed its exact counts")

    for label, field, value in (
        ("normative status", "normative", True),
        ("authorizing status", "authorizing", True),
        ("mutating status", "registry_mutation", True),
        ("history claim", "history_assurance", "ESTABLISHED"),
        ("authentication claim", "review_authentication", "ESTABLISHED"),
        ("optional verifier", "external_verifier_required", False),
    ):
        hostile = copy.deepcopy(status)
        hostile[field] = value
        must_fail(
            lambda value=hostile: validate_status(
                value,
                snapshots[STATUS_SCHEMA_RELATIVE],
                snapshots,
                kit["subject_cut"],
                replay_inputs,
            ),
            label,
        )

    hostile = copy.deepcopy(status)
    hostile["attacker_field"] = True
    must_fail(
        lambda: validate_status(
            hostile,
            snapshots[STATUS_SCHEMA_RELATIVE],
            snapshots,
            kit["subject_cut"],
            replay_inputs,
        ),
        "extra status field",
    )
    for label, member_path, value in (
        (
            "status generator digest substitution",
            ("generated_by", "sha256"),
            "0" * 64,
        ),
        (
            "registry-source digest substitution",
            ("inputs", "registry_source", "sha256"),
            "0" * 64,
        ),
        (
            "registry-source byte-count substitution",
            ("inputs", "registry_source", "bytes"),
            status["inputs"]["registry_source"]["bytes"] + 1,
        ),
        (
            "registry replay digest substitution",
            ("inputs", "registry_replay_inputs", 0, "sha256"),
            "0" * 64,
        ),
        (
            "review-packet digest substitution",
            ("subject", "review_packet", "sha256"),
            "0" * 64,
        ),
        (
            "absolute status input path",
            ("inputs", "registry_source", "path"),
            "/absolute/forged-registry-source.json",
        ),
    ):
        hostile = copy.deepcopy(status)
        target: dict[str, Any] = hostile
        for member in member_path[:-1]:
            target = target[member]
        target[member_path[-1]] = value
        must_fail(
            lambda value=hostile: validate_status(
                value,
                snapshots[STATUS_SCHEMA_RELATIVE],
                snapshots,
                kit["subject_cut"],
                replay_inputs,
            ),
            label,
        )

    hostile = copy.deepcopy(status)
    hostile["inputs"]["registry_replay_inputs"] = hostile["inputs"][
        "registry_replay_inputs"
    ][:-1]
    must_fail(
        lambda: validate_status(
            hostile,
            snapshots[STATUS_SCHEMA_RELATIVE],
            snapshots,
            kit["subject_cut"],
            replay_inputs,
        ),
        "missing registry replay input",
    )
    hostile = copy.deepcopy(status)
    hostile_replay_inputs = hostile["inputs"]["registry_replay_inputs"]
    hostile_replay_inputs[0], hostile_replay_inputs[1] = (
        hostile_replay_inputs[1],
        hostile_replay_inputs[0],
    )
    must_fail(
        lambda: validate_status(
            hostile,
            snapshots[STATUS_SCHEMA_RELATIVE],
            snapshots,
            kit["subject_cut"],
            replay_inputs,
        ),
        "reordered registry replay inputs",
    )

    hostile = copy.deepcopy(status)
    hostile["counts"]["identity_slots_structurally_satisfied"] = 1
    must_fail(
        lambda: validate_status(
            hostile,
            snapshots[STATUS_SCHEMA_RELATIVE],
            snapshots,
            kit["subject_cut"],
            replay_inputs,
        ),
        "incoherent aggregate count",
    )
    hostile = copy.deepcopy(status)
    hostile["decisions"][0]["roles"][0]["suggested_next_slot_id"] = (
        "adr-001.ncp-maintainer.02"
    )
    must_fail(
        lambda: validate_status(
            hostile,
            snapshots[STATUS_SCHEMA_RELATIVE],
            snapshots,
            kit["subject_cut"],
            replay_inputs,
        ),
        "incoherent suggested slot",
    )
    hostile = copy.deepcopy(status)
    hostile["decisions"][0], hostile["decisions"][1] = (
        hostile["decisions"][1],
        hostile["decisions"][0],
    )
    must_fail(
        lambda: validate_status(
            hostile,
            snapshots[STATUS_SCHEMA_RELATIVE],
            snapshots,
            kit["subject_cut"],
            replay_inputs,
        ),
        "reordered status decisions",
    )

    schema = reviewer_kit.parse_object(
        snapshots[STATUS_SCHEMA_RELATIVE],
        STATUS_SCHEMA_RELATIVE,
        MAX_STATUS_SCHEMA_BYTES,
    )
    hostile = copy.deepcopy(status)
    hostile["phase"] = reviewer_kit.REVIEW_CAPTURE_ACTIVE
    must_fail(
        lambda: reviewer_kit.schema_validate(
            schema,
            hostile,
            "active phase with zero records",
            STATUS_SCHEMA_ID,
        ),
        "schema active phase with zero records",
    )
    hostile = copy.deepcopy(mixed_status)
    hostile["phase"] = reviewer_kit.ZERO_REVIEW_ISSUANCE
    must_fail(
        lambda: reviewer_kit.schema_validate(
            schema,
            hostile,
            "zero phase with active records",
            STATUS_SCHEMA_ID,
        ),
        "schema zero phase with active records",
    )
    authority_schema = copy.deepcopy(schema)
    authority_schema["$defs"]["authority"]["properties"]["b01"]["const"] = "GRANTED"
    hostile = copy.deepcopy(status)
    hostile["authority"]["b01"] = "GRANTED"
    must_fail(
        lambda: validate_status(
            hostile,
            encoded(authority_schema),
            snapshots,
            kit["subject_cut"],
            replay_inputs,
        ),
        "co-mutated authority schema and status",
    )
    hostile = copy.deepcopy(projection_generated)
    hostile["decisions"] = hostile["decisions"][:-1]
    must_fail(
        lambda: build_status(
            kit,
            reviewer_kit.ZERO_REVIEW_ISSUANCE,
            projection_snapshots,
            projection_source,
            hostile,
            projection_replay_inputs,
        ),
        "missing decision",
    )
    hostile = copy.deepcopy(projection_generated)
    hostile["decisions"][0], hostile["decisions"][1] = (
        hostile["decisions"][1],
        hostile["decisions"][0],
    )
    must_fail(
        lambda: build_status(
            kit,
            reviewer_kit.ZERO_REVIEW_ISSUANCE,
            projection_snapshots,
            projection_source,
            hostile,
            projection_replay_inputs,
        ),
        "reordered decisions",
    )
    hostile = copy.deepcopy(projection_generated)
    hostile["decisions"][0]["status"] = "ACCEPTED"
    must_fail(
        lambda: build_status(
            kit,
            reviewer_kit.ZERO_REVIEW_ISSUANCE,
            projection_snapshots,
            projection_source,
            hostile,
            projection_replay_inputs,
        ),
        "accepted decision with blockers",
    )
    hostile = copy.deepcopy(projection_generated)
    hostile["review_records"] = [{}]
    must_fail(
        lambda: build_status(
            kit,
            reviewer_kit.REVIEW_CAPTURE_ACTIVE,
            projection_snapshots,
            {**projection_source, "review_records": [{}]},
            hostile,
            projection_replay_inputs,
        ),
        "malformed active record",
    )
    must_fail(
        lambda: build_status(
            kit,
            reviewer_kit.REVIEW_CAPTURE_ACTIVE,
            projection_snapshots,
            projection_source,
            {**projection_generated, "review_records": []},
            projection_replay_inputs,
        ),
        "empty active phase",
    )
    duplicate_phase_record = {"review_id": "duplicate-review"}
    must_fail(
        lambda: reviewer_kit.review_capture_phase_value(
            {
                **projection_source,
                "review_records": [duplicate_phase_record, duplicate_phase_record],
            },
            {
                **projection_generated,
                "review_records": [duplicate_phase_record, duplicate_phase_record],
            },
        ),
        "duplicate review identity",
    )
    over_limit_records = [
        synthetic_record("ADR-001", "ncp-maintainer", ordinal)
        for ordinal in range(1, reviewer_kit.MAX_REVIEW_RECORDS + 2)
    ]
    must_fail(
        lambda: build_status(
            kit,
            reviewer_kit.REVIEW_CAPTURE_ACTIVE,
            projection_snapshots,
            {**projection_source, "review_records": over_limit_records},
            {**projection_generated, "review_records": over_limit_records},
            projection_replay_inputs,
        ),
        "review-record bound plus one",
    )
    must_fail(
        lambda: reviewer_kit.parse_object(
            b'{"schema":"x","schema":"y"}',
            "duplicate status input",
            128,
        ),
        "duplicate JSON member",
    )
    must_fail(
        lambda: reviewer_kit.parse_object(
            b'{"count":1.0}',
            "floating status input",
            128,
        ),
        "floating JSON number",
    )

    exact_generator = reviewer_kit.execute_exact_registry_generator
    replay_count = 0

    def late_transitive_drift(
        *args: Any, **kwargs: Any
    ) -> tuple[dict[str, Any], bytes]:
        nonlocal replay_count
        replay_count += 1
        replayed, serialized = exact_generator(*args, **kwargs)
        if replay_count == 3:
            replayed = copy.deepcopy(replayed)
            replayed["decisions"][0]["title"] += " drift"
        return replayed, serialized

    reviewer_kit.execute_exact_registry_generator = late_transitive_drift
    try:
        must_fail(current_snapshot, "late transitive registry drift")
    finally:
        reviewer_kit.execute_exact_registry_generator = exact_generator
    if replay_count < 3:
        fail("late transitive drift control did not reach the final replay")


def print_text(status: dict[str, Any]) -> None:
    counts = status["counts"]
    print("B01 REVIEW HANDOFF STATUS - CURRENT SNAPSHOT ONLY")
    print(f"phase: {status['phase']}")
    print(
        "decisions: "
        f"{counts['decisions_accepted']}/{counts['decisions_total']} "
        "structurally accepted"
    )
    print(
        "roles: "
        f"{counts['role_obligations_structurally_satisfied']}/"
        f"{counts['role_obligations_total']} structurally satisfied"
    )
    print(
        "identity slots: "
        f"{counts['identity_slots_structurally_satisfied']}/"
        f"{counts['identity_slots_total']} structurally satisfied"
    )
    print(
        "review records: "
        f"{counts['review_records_total']} total, "
        f"{counts['active_review_records']} active, "
        f"{counts['structurally_qualifying_review_records']} qualifying"
    )
    for decision in status["decisions"]:
        shortages = [
            role for role in decision["roles"] if role["minimum_identity_shortage"] > 0
        ]
        suggested_slots = ", ".join(
            role["suggested_next_slot_id"]
            for role in shortages
            if role["suggested_next_slot_id"] is not None
        )
        print(
            f"{decision['adr_id']} {decision['status']}: "
            f"{len(shortages)} role shortages"
            + (f"; suggested {suggested_slots}" if suggested_slots else "")
        )
    print(
        "authority: NOT GRANTED; authentication, independence, history, and "
        "high-water currentness remain external"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate and report the current snapshot (default)",
    )
    parser.add_argument("--json", action="store_true", help="emit status JSON")
    parser.add_argument("--self-test", action="store_true", help="run hostile controls")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        status = build_current_status()
        if args.json:
            sys.stdout.buffer.write(encoded(status))
        else:
            print_text(status)
        return 0
    except (OSError, ReviewHandoffError, reviewer_kit.ReviewerKitError) as error:
        print(f"ERROR B01 review handoff: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
