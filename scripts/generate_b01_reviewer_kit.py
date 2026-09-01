#!/usr/bin/env python3
"""Generate the non-authorizing B01 reviewer preparation kit.

The kit copies immutable machine facts from the retained review request. It
never emits a reviewer identity, decision, timestamp, evidence reference, or
task transition. Response materialization validates one human-supplied record
and writes only a structural candidate to stdout.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import types
from pathlib import Path
from typing import Any, NoReturn

from bounded_json import (
    BoundedJsonError,
    FileSnapshotLimits,
    JsonLimits,
    parse_json_bytes,
    read_bounded_regular_file,
    validate_native_json_tree,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_RELATIVE = "scripts/generate_b01_reviewer_kit.py"
REQUEST_RELATIVE = "evidence/implementation/requests/B01/review-request.v1.json"
REQUEST_GENERATOR_RELATIVE = "scripts/generate_b01_review_request.py"
IMMUTABLE_GIT_RELATIVE = "scripts/immutable_git.py"
KIT_SCHEMA_RELATIVE = "evidence/implementation/requests/B01/reviewer-kit.schema.v1.json"
RESPONSE_SCHEMA_RELATIVE = (
    "evidence/implementation/requests/B01/review-response.schema.v1.json"
)
CANDIDATE_SCHEMA_RELATIVE = (
    "evidence/implementation/requests/B01/review-source-candidate.schema.v1.json"
)
OUTPUT_RELATIVE = "evidence/implementation/requests/B01/reviewer-kit.v1.json"
REGISTRY_GENERATOR_RELATIVE = "scripts/generate_decision_registry.py"
REGISTRY_SCHEMA_RELATIVE = "docs/adr/decision-registry.proposed.schema.v1.json"
CURRENT_PROPOSED_REGISTRY_RELATIVE = "docs/adr/decision-registry.proposed.v1.json"
REGISTRY_SOURCE_RELATIVE = "docs/adr/decision-registry.source.v1.json"
REVIEW_PACKET_RELATIVE = "docs/adr/B01_REVIEW_PACKET.md"

KIT_SCHEMA = "ncp.b01-reviewer-kit.v1"
RESPONSE_SCHEMA = "ncp.b01-review-response.v1"
CANDIDATE_SCHEMA = "ncp.b01-review-source-candidate.v1"
KIT_SCHEMA_ID = "https://sepahead.github.io/NCP/schemas/b01-reviewer-kit.v1.json"
RESPONSE_SCHEMA_ID = (
    "https://sepahead.github.io/NCP/schemas/b01-review-response.v1.json"
)
CANDIDATE_SCHEMA_ID = (
    "https://sepahead.github.io/NCP/schemas/b01-review-source-candidate.v1.json"
)
REQUEST_SCHEMA = "ncp.b01-review-request.v1"
REGISTRY_SOURCE_SCHEMA = "ncp.proposed-decision-registry-source.v1"
ZERO_REVIEW_ISSUANCE = "ZERO_REVIEW_ISSUANCE"
REVIEW_CAPTURE_ACTIVE = "REVIEW_CAPTURE_ACTIVE"
EXPECTED_REQUEST_SHA256 = (
    "af8daf9ff4ab42969b729ddc20eeb7ba45bfd11648d748605a6422b804663829"
)
EXPECTED_REQUEST_BYTES = 135_557
KIT_CLAIM_BOUNDARY = (
    "STRUCTURAL_REVIEW_PREPARATION_ONLY_NO_REVIEWER_DECISION_IDENTITY_ROLE_"
    "AUTHORITY_INDEPENDENCE_EVIDENCE_AUTHENTICATION_ADR_ACCEPTANCE_TASK_STATUS_"
    "PROTOCOL_CHANGE_OR_RELEASE_AUTHORITY"
)
MATERIALIZATION_CLAIM_BOUNDARY = (
    "STRUCTURAL_VALIDATION_ONLY_NO_AUTHORSHIP_ROLE_AUTHORITY_INDEPENDENCE_"
    "EXTERNAL_RECEIPT_ADR_ACCEPTANCE_TASK_STATUS_OR_RELEASE_AUTHORITY"
)
CANDIDATE_CLAIM_BOUNDARY = (
    "UNAUTHENTICATED_STRUCTURAL_CANDIDATE_ONLY_EXTERNAL_VERIFIER_MUST_ESTABLISH_"
    "AUTHORSHIP_ROLE_AUTHORITY_INDEPENDENCE_RECEIPT_CURRENTNESS_AND_ADMISSION_"
    "NO_ADR_TASK_PROTOCOL_OR_RELEASE_AUTHORITY"
)
SAFE_EVIDENCE_PATH_PATTERN = (
    r"^evidence/implementation/reviews/B01/"
    r"(?!\.\.(?:/|$))(?!.*(?:^|/)\.\.(?:/|$))[^\\]+$"
)
MACHINE_MEMBERS = ("adr_id", "role_id", "subject")
HUMAN_MEMBERS = (
    "review_id",
    "reviewer",
    "decision",
    "conditions",
    "role_authorization",
    "independence_assessment",
    "external_receipt",
    "timestamp_utc",
    "supersedes",
)
EXPECTED_COUNTS = {
    "decisions": 11,
    "role_obligations": 52,
    "minimum_identity_slots": 53,
    "independent_obligations": 5,
    "minimum_independent_identity_slots": 6,
    "minimum_evidence_requirements": 112,
}
EXPECTED_ORDERING = (
    "PACKET_DECISION_ORDER_THEN_REQUIRED_REVIEW_ORDER_THEN_ONE_BASED_IDENTITY_ORDINAL"
)
EVIDENCE_PREFIX = "evidence/implementation/reviews/B01/"
EVIDENCE_KINDS = (
    "ROLE_AUTHORIZATION",
    "EXTERNAL_REVIEW_RECEIPT",
    "INDEPENDENCE_ASSESSMENT",
)
EXPECTED_SOURCE_FIELDS = (
    "review_id",
    "adr_id",
    "role_id",
    "reviewer",
    "subject",
    "decision",
    "conditions",
    "role_authorization",
    "independence_assessment",
    "external_receipt",
    "timestamp_utc",
    "supersedes",
)
EXPECTED_EVIDENCE_FIELDS = ("url", "path", "sha256", "bytes", "media_type")
EXPECTED_DECISION_IDS = tuple(f"ADR-{number:03d}" for number in range(1, 12))

MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_SCHEMA_BYTES = 128 * 1024
MAX_SCRIPT_BYTES = 512 * 1024
MAX_KIT_BYTES = 512 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_ITEMS = 100_000
MAX_OBJECT_MEMBERS = 256
MAX_ARRAY_ITEMS = 4_096
MAX_KEY_BYTES = 128
MAX_STRING_BYTES = 4_096
MAX_REVIEW_RECORDS = 256

HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
HEX40 = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
ADR_ID = re.compile(r"^ADR-(?:00[1-9]|01[01])$", re.ASCII)
ROLE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", re.ASCII)
SLOT_ID = re.compile(
    r"^adr-(?:00[1-9]|01[01])\.[a-z0-9]+(?:-[a-z0-9]+)*\.[0-9]{2}$",
    re.ASCII,
)
EVIDENCE_ID = re.compile(
    r"^adr-(?:00[1-9]|01[01])\.[a-z0-9]+(?:-[a-z0-9]+)*\.[0-9]{2}\."
    r"(?:role-authorization|external-review-receipt|independence-assessment)$",
    re.ASCII,
)


class ReviewerKitError(RuntimeError):
    """The reviewer kit cannot be generated or validated safely."""


def fail(message: str) -> NoReturn:
    raise ReviewerKitError(message)


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


def exact_text(
    value: Any,
    path: str,
    *,
    minimum: int = 1,
    maximum: int = MAX_STRING_BYTES,
) -> str:
    if type(value) is not str:
        fail(f"{path} must be text")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise ReviewerKitError(f"{path} is not valid UTF-8") from error
    if not minimum <= size <= maximum:
        fail(f"{path} text length is outside {minimum}..{maximum} bytes")
    return value


def json_limits(maximum_bytes: int) -> JsonLimits:
    return JsonLimits(
        maximum_bytes=maximum_bytes,
        maximum_depth=MAX_JSON_DEPTH,
        maximum_items=MAX_JSON_ITEMS,
        maximum_object_members=MAX_OBJECT_MEMBERS,
        maximum_array_items=MAX_ARRAY_ITEMS,
        maximum_key_utf8_bytes=min(MAX_KEY_BYTES, maximum_bytes),
        maximum_string_utf8_bytes=min(MAX_STRING_BYTES, maximum_bytes),
        maximum_total_string_utf8_bytes=maximum_bytes,
        maximum_integer_chars=128,
        maximum_float_chars=128,
        allow_floats=False,
    )


def read_file(relative: str, maximum_bytes: int) -> bytes:
    try:
        return read_bounded_regular_file(
            ROOT / relative,
            limits=FileSnapshotLimits(minimum_bytes=1, maximum_bytes=maximum_bytes),
            label=relative,
        )
    except BoundedJsonError as error:
        fail(str(error))


def parse_object(raw: bytes, label: str, maximum_bytes: int) -> dict[str, Any]:
    try:
        value = parse_json_bytes(
            raw,
            limits=json_limits(maximum_bytes),
            label=label,
        )
    except BoundedJsonError as error:
        fail(str(error))
    if type(value) is not dict:
        fail(f"{label} must contain one JSON object")
    return value


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def identity(relative: str, raw: bytes) -> dict[str, str | int]:
    return {"path": relative, "sha256": sha256(raw), "bytes": len(raw)}


def generated_bytes(value: dict[str, Any]) -> bytes:
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
        raise ReviewerKitError(f"cannot encode reviewer kit: {error}") from error
    if len(raw) > MAX_KIT_BYTES:
        fail(f"generated reviewer kit exceeds {MAX_KIT_BYTES} bytes")
    return raw


def schema_validate(
    schema: dict[str, Any],
    instance: dict[str, Any],
    label: str,
    expected_schema_id: str,
) -> None:
    try:
        from validate_evidence_schemas import (
            EvidenceSchemaError,
            require_pinned_validator,
            validate_instance,
        )

        require_pinned_validator()
        validate_instance(
            schema,
            instance,
            label,
            expected_schema_id=expected_schema_id,
        )
    except (ImportError, EvidenceSchemaError) as error:
        fail(str(error))


def validate_schema_projection(
    kit_schema: dict[str, Any],
    response_schema: dict[str, Any],
    candidate_schema: dict[str, Any],
    registry_schema: dict[str, Any],
) -> None:
    response_defs = exact_keys(
        response_schema.get("$defs"),
        {
            "sha256",
            "identity",
            "timestamp",
            "evidenceRef",
            "reviewer",
            "closure",
            "condition",
        },
        "response schema $defs",
    )
    registry_defs = registry_schema.get("$defs")
    if type(registry_defs) is not dict:
        fail("registry schema $defs must be one object")
    for name in response_defs:
        expected_definition = copy.deepcopy(registry_defs.get(name))
        if name == "evidenceRef" and type(expected_definition) is dict:
            expected_definition["properties"]["path"]["pattern"] = (
                SAFE_EVIDENCE_PATH_PATTERN
            )
        if response_defs[name] != expected_definition:
            fail(f"response schema definition {name} differs from registry policy")

    response_properties = response_schema.get("properties")
    if type(response_properties) is not dict:
        fail("response schema properties must be one object")
    expected_response_properties = {"schema", "slot_id", *HUMAN_MEMBERS}
    if set(response_properties) != expected_response_properties:
        fail("response schema root fields differ from the human response contract")
    review_properties = registry_defs.get("reviewRecord", {}).get("properties")
    if type(review_properties) is not dict:
        fail("registry review-record properties are missing")
    for name in HUMAN_MEMBERS:
        if response_properties[name] != review_properties.get(name):
            fail(f"response schema property {name} differs from registry policy")
    if response_schema.get("required") != [
        "schema",
        "slot_id",
        *HUMAN_MEMBERS,
    ]:
        fail("response schema required fields or ordering changed")

    kit_defs = kit_schema.get("$defs")
    if type(kit_defs) is not dict:
        fail("reviewer-kit schema $defs must be one object")
    for name in (
        "sha256",
        "gitObject",
        "roleId",
        "fileIdentity",
        "adrSource",
        "adrSourceSet",
        "reviewSubject",
    ):
        if kit_defs.get(name) != registry_defs.get(name):
            fail(f"reviewer-kit schema definition {name} differs from registry policy")

    candidate_defs = exact_keys(
        candidate_schema.get("$defs"),
        {
            "sha256",
            "gitObject",
            "fileIdentity",
            "validationContext",
            "adrSource",
            "adrSourceSet",
            "roleId",
            "identity",
            "timestamp",
            "evidenceRef",
            "reviewer",
            "reviewSubject",
            "closure",
            "condition",
            "sourceRecord",
        },
        "candidate schema $defs",
    )
    for name in (
        "sha256",
        "gitObject",
        "fileIdentity",
        "adrSource",
        "adrSourceSet",
        "roleId",
        "identity",
        "timestamp",
        "evidenceRef",
        "reviewer",
        "reviewSubject",
        "closure",
        "condition",
    ):
        expected_definition = copy.deepcopy(registry_defs.get(name))
        if name == "evidenceRef" and type(expected_definition) is dict:
            expected_definition["properties"]["path"]["pattern"] = (
                SAFE_EVIDENCE_PATH_PATTERN
            )
        if candidate_defs[name] != expected_definition:
            fail(f"candidate schema definition {name} differs from registry policy")

    expected_source_record = copy.deepcopy(registry_defs.get("reviewRecord"))
    if type(expected_source_record) is not dict:
        fail("registry review-record definition is missing")
    expected_source_record["required"].remove("derived")
    del expected_source_record["properties"]["derived"]
    observed_source_record = copy.deepcopy(candidate_defs["sourceRecord"])
    observed_conditional = observed_source_record.pop("allOf", None)
    if observed_source_record != expected_source_record:
        fail("candidate source record differs from the registry-source projection")
    if observed_conditional != [
        {
            "if": {
                "properties": {
                    "decision": {"const": "ACCEPT_WITH_CONDITIONS"},
                },
                "required": ["decision"],
            },
            "then": {"properties": {"conditions": {"minItems": 1}}},
            "else": {"properties": {"conditions": {"maxItems": 0}}},
        }
    ]:
        fail("candidate source-record decision conditional changed")

    candidate_properties = candidate_schema.get("properties")
    if type(candidate_properties) is not dict or set(candidate_properties) != {
        "schema",
        "normative",
        "authorizing",
        "claim_boundary",
        "slot_id",
        "validation_context",
        "registry_mutation",
        "external_verifier_required",
        "source_record",
    }:
        fail("candidate schema root fields differ from the handoff contract")
    if candidate_schema.get("required") != [
        "schema",
        "normative",
        "authorizing",
        "claim_boundary",
        "slot_id",
        "validation_context",
        "registry_mutation",
        "external_verifier_required",
        "source_record",
    ]:
        fail("candidate schema required fields or ordering changed")
    expected_candidate_properties = {
        "schema": {"const": CANDIDATE_SCHEMA},
        "normative": {"const": False},
        "authorizing": {"const": False},
        "claim_boundary": {"const": CANDIDATE_CLAIM_BOUNDARY},
        "slot_id": copy.deepcopy(response_properties["slot_id"]),
        "validation_context": {"$ref": "#/$defs/validationContext"},
        "registry_mutation": {"const": False},
        "external_verifier_required": {"const": True},
        "source_record": {"$ref": "#/$defs/sourceRecord"},
    }
    if candidate_properties != expected_candidate_properties:
        fail("candidate schema root policy changed")
    expected_context_properties = {}
    for name, path in (
        ("reviewer_kit", OUTPUT_RELATIVE),
        ("candidate_schema", CANDIDATE_SCHEMA_RELATIVE),
        ("registry_generator", REGISTRY_GENERATOR_RELATIVE),
        ("validated_against_registry_source", REGISTRY_SOURCE_RELATIVE),
    ):
        expected_context_properties[name] = {
            "allOf": [
                {"$ref": "#/$defs/fileIdentity"},
                {"properties": {"path": {"const": path}}},
            ]
        }
    if candidate_defs["validationContext"] != {
        "type": "object",
        "additionalProperties": False,
        "required": list(expected_context_properties),
        "properties": expected_context_properties,
    }:
        fail("candidate schema validation context changed")

    stack: list[Any] = [response_schema, candidate_schema]
    while stack:
        value = stack.pop()
        if type(value) is dict:
            forbidden = set(value) & {"default", "examples", "example"}
            if forbidden:
                fail(f"response schema contains forbidden population aid {forbidden}")
            stack.extend(value.values())
        elif type(value) is list:
            stack.extend(value)


def validate_request(
    request: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    exact_keys(
        request,
        {
            "schema",
            "normative",
            "authorizing",
            "minimum_only",
            "claim_boundary",
            "generated_by",
            "subject_cut",
            "counts",
            "ordering",
            "human_response_contract",
            "review_slots",
            "evidence_requirements",
        },
        "review request",
    )
    if request["schema"] != REQUEST_SCHEMA:
        fail("review request schema is not supported")
    if (
        request["normative"] is not False
        or request["authorizing"] is not False
        or request["minimum_only"] is not True
    ):
        fail("review request overclaims authority or changes its minimum roster")
    if request["counts"] != EXPECTED_COUNTS:
        fail("review request counts differ from the fixed minimum roster")
    if request["ordering"] != EXPECTED_ORDERING:
        fail("review request ordering policy changed")

    response_contract = exact_keys(
        request["human_response_contract"],
        {
            "conditional_or_superseding_evidence",
            "decision_population",
            "evidence_population",
            "evidence_reference_fields",
            "source_record_fields",
        },
        "review request human_response_contract",
    )
    if response_contract != {
        "conditional_or_superseding_evidence": "ADDITIONAL_AND_NOT_PREALLOCATED",
        "decision_population": "HUMAN_REVIEWER_ONLY_MODEL_OR_AUTOMATION_FORBIDDEN",
        "evidence_population": "HUMAN_OR_AUTHENTICATED_NON_MODEL_SYSTEM_ONLY",
        "evidence_reference_fields": list(EXPECTED_EVIDENCE_FIELDS),
        "source_record_fields": list(EXPECTED_SOURCE_FIELDS),
    }:
        fail("review request human response contract changed")

    slots = request["review_slots"]
    evidence = request["evidence_requirements"]
    if (
        type(slots) is not list
        or len(slots) != EXPECTED_COUNTS["minimum_identity_slots"]
    ):
        fail("review request slot count changed")
    if (
        type(evidence) is not list
        or len(evidence) != EXPECTED_COUNTS["minimum_evidence_requirements"]
    ):
        fail("review request evidence count changed")

    evidence_by_id: dict[str, dict[str, Any]] = {}
    for index, requirement in enumerate(evidence):
        path = f"review request evidence_requirements[{index}]"
        exact_keys(
            requirement,
            {
                "evidence_requirement_id",
                "exclusive",
                "kind",
                "required_path_prefix",
                "review_slot_id",
                "state",
            },
            path,
        )
        requirement_id = exact_text(
            requirement["evidence_requirement_id"],
            f"{path}.evidence_requirement_id",
            maximum=160,
        )
        if EVIDENCE_ID.fullmatch(requirement_id) is None:
            fail(f"{path}.evidence_requirement_id is not canonical")
        if requirement_id in evidence_by_id:
            fail(f"review request duplicates evidence ID {requirement_id}")
        if (
            requirement["exclusive"] is not True
            or requirement["required_path_prefix"] != EVIDENCE_PREFIX
            or requirement["state"] != "UNFILLED"
            or requirement["kind"] not in EVIDENCE_KINDS
        ):
            fail(f"{path} changes the unfilled exclusive evidence contract")
        evidence_by_id[requirement_id] = requirement

    subjects: dict[str, dict[str, Any]] = {}
    slot_ids: set[str] = set()
    role_obligations: set[tuple[str, str]] = set()
    independent_obligations: set[tuple[str, str]] = set()
    independent_slots = 0
    consumed_evidence: list[str] = []
    for index, slot in enumerate(slots):
        path = f"review request review_slots[{index}]"
        exact_keys(
            slot,
            {
                "adr_id",
                "distinct_identity_group",
                "identity_ordinal",
                "required_evidence_ids",
                "requires_independence",
                "role_id",
                "role_label",
                "slot_id",
                "state",
                "subject",
            },
            path,
        )
        slot_id = exact_text(slot["slot_id"], f"{path}.slot_id", maximum=96)
        adr_id = exact_text(slot["adr_id"], f"{path}.adr_id", maximum=7)
        role_id = exact_text(slot["role_id"], f"{path}.role_id", maximum=64)
        if SLOT_ID.fullmatch(slot_id) is None or slot_id in slot_ids:
            fail(f"{path}.slot_id is invalid or duplicated")
        if ADR_ID.fullmatch(adr_id) is None or ROLE_ID.fullmatch(role_id) is None:
            fail(f"{path} has an invalid ADR or role ID")
        if slot["state"] != "UNFILLED":
            fail(f"{path} is not unfilled")
        if type(slot["requires_independence"]) is not bool:
            fail(f"{path}.requires_independence must be boolean")
        ordinal = slot["identity_ordinal"]
        if type(ordinal) is not int or not 1 <= ordinal <= 32:
            fail(f"{path}.identity_ordinal is outside 1..32")
        exact_text(
            slot["distinct_identity_group"],
            f"{path}.distinct_identity_group",
            maximum=96,
        )
        exact_text(slot["role_label"], f"{path}.role_label", maximum=128)

        required_ids = slot["required_evidence_ids"]
        expected_kinds = list(EVIDENCE_KINDS[:2])
        if slot["requires_independence"]:
            expected_kinds.append(EVIDENCE_KINDS[2])
            independent_slots += 1
            independent_obligations.add((adr_id, role_id))
        if type(required_ids) is not list or len(required_ids) != len(expected_kinds):
            fail(f"{path}.required_evidence_ids has the wrong length")
        observed_kinds: list[str] = []
        for requirement_id in required_ids:
            requirement = evidence_by_id.get(requirement_id)
            if requirement is None or requirement["review_slot_id"] != slot_id:
                fail(f"{path} references missing or cross-slot evidence")
            observed_kinds.append(requirement["kind"])
            consumed_evidence.append(requirement_id)
        if observed_kinds != expected_kinds:
            fail(f"{path} evidence kinds or ordering changed")

        subject = slot["subject"]
        exact_keys(
            subject,
            {
                "decision_set_sha256",
                "adr_content_sha256",
                "adr_bytes",
                "adr_source_set",
                "source_commit",
                "source_tree",
                "review_packet_sha256",
            },
            f"{path}.subject",
        )
        if (
            subject["decision_set_sha256"]
            != request["subject_cut"]["decision_set_sha256"]
        ):
            fail(f"{path}.subject decision set differs from the request cut")
        if (
            subject["review_packet_sha256"]
            != request["subject_cut"]["review_packet"]["sha256"]
        ):
            fail(f"{path}.subject packet differs from the request cut")
        if (
            subject["source_commit"]
            != request["subject_cut"]["zero_review_source_commit"]
        ):
            fail(f"{path}.subject source commit differs from the request cut")
        if subject["source_tree"] != request["subject_cut"]["zero_review_source_tree"]:
            fail(f"{path}.subject source tree differs from the request cut")
        if subject["adr_source_set"].get("decision_id") != adr_id:
            fail(f"{path}.subject source set names another ADR")
        if adr_id in subjects and subjects[adr_id] != subject:
            fail(f"review request contains multiple subjects for {adr_id}")
        subjects.setdefault(adr_id, copy.deepcopy(subject))
        slot_ids.add(slot_id)
        role_obligations.add((adr_id, role_id))

    if tuple(subjects) != EXPECTED_DECISION_IDS:
        fail("review request ADR ordering or coverage changed")
    if len(role_obligations) != EXPECTED_COUNTS["role_obligations"]:
        fail("review request role-obligation count changed")
    if len(independent_obligations) != EXPECTED_COUNTS["independent_obligations"]:
        fail("review request independent-obligation count changed")
    if independent_slots != EXPECTED_COUNTS["minimum_independent_identity_slots"]:
        fail("review request independent-slot count changed")
    if consumed_evidence != list(evidence_by_id):
        fail("review request evidence order, coverage, or uniqueness changed")
    return slots, evidence


def validate_request_bindings(
    request: dict[str, Any], snapshots: dict[str, bytes]
) -> None:
    if identity(REQUEST_RELATIVE, snapshots[REQUEST_RELATIVE]) != {
        "path": REQUEST_RELATIVE,
        "sha256": EXPECTED_REQUEST_SHA256,
        "bytes": EXPECTED_REQUEST_BYTES,
    }:
        fail("review request differs from the exact retained immutable bytes")
    expected_generators = [
        identity(REQUEST_GENERATOR_RELATIVE, snapshots[REQUEST_GENERATOR_RELATIVE]),
        identity(IMMUTABLE_GIT_RELATIVE, snapshots[IMMUTABLE_GIT_RELATIVE]),
    ]
    if request["generated_by"] != expected_generators:
        fail("review request generator identities differ from current exact bytes")
    subject_cut = request["subject_cut"]
    if subject_cut.get("review_packet") != identity(
        REVIEW_PACKET_RELATIVE, snapshots[REVIEW_PACKET_RELATIVE]
    ):
        fail("review request packet identity differs from current exact bytes")
    # The request binds the zero-review proposed registry as historical subject
    # identity. Do not compare that identity with the live proposed registry.
    # Authentic review records can evolve the live registry without changing
    # the immutable request or its frozen review subject.


def build_kit_from_snapshots(snapshots: dict[str, bytes]) -> dict[str, Any]:
    request = parse_object(
        snapshots[REQUEST_RELATIVE], REQUEST_RELATIVE, MAX_REQUEST_BYTES
    )
    kit_schema = parse_object(
        snapshots[KIT_SCHEMA_RELATIVE], KIT_SCHEMA_RELATIVE, MAX_SCHEMA_BYTES
    )
    response_schema = parse_object(
        snapshots[RESPONSE_SCHEMA_RELATIVE], RESPONSE_SCHEMA_RELATIVE, MAX_SCHEMA_BYTES
    )
    candidate_schema = parse_object(
        snapshots[CANDIDATE_SCHEMA_RELATIVE],
        CANDIDATE_SCHEMA_RELATIVE,
        MAX_SCHEMA_BYTES,
    )
    registry_schema = parse_object(
        snapshots[REGISTRY_SCHEMA_RELATIVE], REGISTRY_SCHEMA_RELATIVE, MAX_INPUT_BYTES
    )
    validate_schema_projection(
        kit_schema,
        response_schema,
        candidate_schema,
        registry_schema,
    )
    slots, evidence = validate_request(request)
    validate_request_bindings(request, snapshots)
    evidence_by_id = {
        requirement["evidence_requirement_id"]: requirement for requirement in evidence
    }

    decisions: list[dict[str, Any]] = []
    seen_decisions: set[str] = set()
    generated_slots: list[dict[str, Any]] = []
    for slot in slots:
        if slot["adr_id"] not in seen_decisions:
            decisions.append(
                {
                    "adr_id": slot["adr_id"],
                    "subject": copy.deepcopy(slot["subject"]),
                }
            )
            seen_decisions.add(slot["adr_id"])
        generated_slots.append(
            {
                "slot_id": slot["slot_id"],
                "adr_id": slot["adr_id"],
                "distinct_identity_group": slot["distinct_identity_group"],
                "identity_ordinal": slot["identity_ordinal"],
                "role_id": slot["role_id"],
                "role_label": slot["role_label"],
                "requires_independence": slot["requires_independence"],
                "required_evidence": [
                    {
                        "evidence_requirement_id": requirement_id,
                        "kind": evidence_by_id[requirement_id]["kind"],
                        "required_path_prefix": evidence_by_id[requirement_id][
                            "required_path_prefix"
                        ],
                        "exclusive": evidence_by_id[requirement_id]["exclusive"],
                    }
                    for requirement_id in slot["required_evidence_ids"]
                ],
            }
        )

    kit = {
        "schema": KIT_SCHEMA,
        "normative": False,
        "authorizing": False,
        "minimum_only": True,
        "claim_boundary": KIT_CLAIM_BOUNDARY,
        "generated_by": identity(SCRIPT_RELATIVE, snapshots[SCRIPT_RELATIVE]),
        "inputs": {
            "review_request": identity(REQUEST_RELATIVE, snapshots[REQUEST_RELATIVE]),
            "reviewer_kit_schema": identity(
                KIT_SCHEMA_RELATIVE, snapshots[KIT_SCHEMA_RELATIVE]
            ),
            "review_response_schema": identity(
                RESPONSE_SCHEMA_RELATIVE, snapshots[RESPONSE_SCHEMA_RELATIVE]
            ),
            "review_source_candidate_schema": identity(
                CANDIDATE_SCHEMA_RELATIVE,
                snapshots[CANDIDATE_SCHEMA_RELATIVE],
            ),
            "decision_registry_generator": identity(
                REGISTRY_GENERATOR_RELATIVE,
                snapshots[REGISTRY_GENERATOR_RELATIVE],
            ),
            "decision_registry_schema": identity(
                REGISTRY_SCHEMA_RELATIVE, snapshots[REGISTRY_SCHEMA_RELATIVE]
            ),
        },
        "subject_cut": copy.deepcopy(request["subject_cut"]),
        "counts": copy.deepcopy(request["counts"]),
        "ordering": request["ordering"],
        "materialization_contract": {
            "response_selector": "slot_id",
            "machine_injected_source_members": list(MACHINE_MEMBERS),
            "human_response_members": list(HUMAN_MEMBERS),
            "derived_member_forbidden": True,
            "registry_mutation": False,
            "output": "STDOUT_ONLY_STRUCTURAL_CANDIDATE",
            "output_schema": CANDIDATE_SCHEMA,
            "claim_boundary": MATERIALIZATION_CLAIM_BOUNDARY,
        },
        "decisions": decisions,
        "slots": generated_slots,
    }
    validate_kit(kit, kit_schema)
    return kit


def input_limits(relative: str) -> int:
    if relative == REQUEST_RELATIVE:
        return MAX_REQUEST_BYTES
    if relative in {
        KIT_SCHEMA_RELATIVE,
        RESPONSE_SCHEMA_RELATIVE,
        CANDIDATE_SCHEMA_RELATIVE,
    }:
        return MAX_SCHEMA_BYTES
    if relative == SCRIPT_RELATIVE:
        return MAX_SCRIPT_BYTES
    return MAX_INPUT_BYTES


def snapshot_inputs() -> dict[str, bytes]:
    paths = (
        SCRIPT_RELATIVE,
        REQUEST_RELATIVE,
        KIT_SCHEMA_RELATIVE,
        RESPONSE_SCHEMA_RELATIVE,
        CANDIDATE_SCHEMA_RELATIVE,
        REQUEST_GENERATOR_RELATIVE,
        IMMUTABLE_GIT_RELATIVE,
        REGISTRY_GENERATOR_RELATIVE,
        REGISTRY_SCHEMA_RELATIVE,
        REVIEW_PACKET_RELATIVE,
    )
    return {relative: read_file(relative, input_limits(relative)) for relative in paths}


def validate_retained_issuance(
    request: dict[str, Any], snapshots: dict[str, bytes]
) -> None:
    module_name = "_ncp_b01_exact_immutable_git"
    prior_module = sys.modules.get(module_name)
    module = types.ModuleType(module_name)
    module.__file__ = str(ROOT / IMMUTABLE_GIT_RELATIVE)
    sys.modules[module_name] = module
    try:
        source_text = snapshots[IMMUTABLE_GIT_RELATIVE].decode("utf-8", errors="strict")
        code = compile(
            source_text,
            IMMUTABLE_GIT_RELATIVE,
            "exec",
            dont_inherit=True,
            optimize=0,
        )
        exec(code, module.__dict__)  # noqa: S102 - exact request-bound bytes
        control_output = module.__dict__.get("control_output")
        require_ancestor = module.__dict__.get("require_ancestor")
        commit_tree = module.__dict__.get("commit_tree")
        blob_snapshot = module.__dict__.get("blob_snapshot")
        if not all(
            callable(function)
            for function in (
                control_output,
                require_ancestor,
                commit_tree,
                blob_snapshot,
            )
        ):
            fail("exact immutable Git helper lacks the retained-cut API")

        head_raw = control_output(
            ["rev-parse", "--verify", "HEAD^{commit}"],
            root=ROOT,
            maximum=64,
            label="B01 reviewer-kit checkout HEAD",
        )
        try:
            head_text = head_raw.decode("ascii", errors="strict")
        except UnicodeDecodeError as error:
            raise ReviewerKitError("checkout HEAD is not ASCII") from error
        if not head_text.endswith("\n") or HEX40.fullmatch(head_text[:-1]) is None:
            fail("checkout HEAD is not one canonical SHA-1 commit")
        head_commit = head_text[:-1]

        subject_cut = request["subject_cut"]
        issuance = subject_cut["issuance_currentness"]
        issuance_commit = issuance["resolved_commit"]
        packet_commit = subject_cut["packet_commit"]
        source_commit = subject_cut["zero_review_source_commit"]
        for label, value in (
            ("issuance commit", issuance_commit),
            ("packet commit", packet_commit),
            ("zero-review source commit", source_commit),
        ):
            if type(value) is not str or HEX40.fullmatch(value) is None:
                fail(f"retained {label} is not canonical")

        require_ancestor(
            issuance_commit,
            head_commit,
            root=ROOT,
            allow_equal=True,
            label="retained B01 request issuance lineage",
        )
        require_ancestor(
            packet_commit,
            issuance_commit,
            root=ROOT,
            allow_equal=False,
            label="immutable B01 packet issuance lineage",
        )
        require_ancestor(
            source_commit,
            packet_commit,
            root=ROOT,
            allow_equal=False,
            label="zero-review B01 source lineage",
        )
        if commit_tree(issuance_commit, root=ROOT) != issuance["resolved_tree"]:
            fail("retained issuance tree differs from the immutable request")
        if commit_tree(packet_commit, root=ROOT) != subject_cut["packet_tree"]:
            fail("retained packet tree differs from the immutable request")
        if (
            commit_tree(source_commit, root=ROOT)
            != subject_cut["zero_review_source_tree"]
        ):
            fail("retained zero-review tree differs from the immutable request")

        for generated_by in request["generated_by"]:
            retained = blob_snapshot(
                issuance_commit,
                generated_by["path"],
                maximum=MAX_SCRIPT_BYTES,
                root=ROOT,
            )
            if retained.identity() != generated_by:
                fail("retained request generator bytes differ from issuance")

        retained_packet = blob_snapshot(
            packet_commit,
            REVIEW_PACKET_RELATIVE,
            maximum=MAX_INPUT_BYTES,
            root=ROOT,
        )
        if retained_packet.identity() != subject_cut["review_packet"]:
            fail("retained review packet bytes differ from the request")

        retained_registry = blob_snapshot(
            issuance_commit,
            CURRENT_PROPOSED_REGISTRY_RELATIVE,
            maximum=MAX_INPUT_BYTES,
            root=ROOT,
        )
        if retained_registry.identity() != subject_cut["proposed_registry"]:
            fail("retained zero-review registry differs from the request")
        registry = parse_object(
            retained_registry.raw,
            f"{issuance_commit}:{CURRENT_PROPOSED_REGISTRY_RELATIVE}",
            MAX_INPUT_BYTES,
        )
        if (
            registry.get("review_records") != []
            or registry.get("review_packet") != subject_cut["review_packet"]
            or registry.get("decision_set", {}).get("sha256")
            != subject_cut["decision_set_sha256"]
        ):
            fail("retained issuance registry changed its zero-review subject")
        retained_source_identity = registry.get("source")
        if type(retained_source_identity) is not dict:
            fail("retained issuance registry lacks its source identity")
        retained_source = blob_snapshot(
            source_commit,
            REGISTRY_SOURCE_RELATIVE,
            maximum=MAX_INPUT_BYTES,
            root=ROOT,
        )
        if retained_source.identity() != retained_source_identity:
            fail("retained zero-review source differs from the issuance registry")

        source_identities: dict[str, dict[str, Any]] = {}
        for slot in request["review_slots"]:
            for source in slot["subject"]["adr_source_set"]["sources"]:
                source_identity = {
                    "path": source["path"],
                    "sha256": source["sha256"],
                    "bytes": source["bytes"],
                }
                prior = source_identities.setdefault(source["path"], source_identity)
                if prior != source_identity:
                    fail("retained request has conflicting ADR source identities")
        for relative, expected in source_identities.items():
            observed = blob_snapshot(
                source_commit,
                relative,
                maximum=MAX_INPUT_BYTES,
                root=ROOT,
            )
            if observed.identity() != expected:
                fail(f"retained ADR source differs from the request: {relative}")
        final_head_raw = control_output(
            ["rev-parse", "--verify", "HEAD^{commit}"],
            root=ROOT,
            maximum=64,
            label="final B01 reviewer-kit checkout HEAD",
        )
        if final_head_raw != head_raw:
            fail("checkout HEAD moved during retained-issuance validation")
    except ReviewerKitError:
        raise
    except (
        AttributeError,
        KeyError,
        MemoryError,
        OSError,
        RuntimeError,
        SyntaxError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as error:
        fail(f"retained B01 issuance validation failed: {error}")
    finally:
        if prior_module is None:
            del sys.modules[module_name]
        else:
            sys.modules[module_name] = prior_module


def load_retained_request_snapshot(
    request_module: types.ModuleType,
    request: dict[str, Any],
) -> dict[str, Any]:
    load_snapshot = request_module.__dict__.get("load_snapshot")
    original_resolver = request_module.__dict__.get("resolve_checkout_head")
    if not callable(load_snapshot) or not callable(original_resolver):
        fail("exact retained request generator lacks its snapshot API")
    issuance = request["subject_cut"]["issuance_currentness"]
    issuance_commit = issuance["resolved_commit"]
    issuance_tree = issuance["resolved_tree"]
    resolver_calls = 0

    def resolve_retained_checkout(*, root: Path = ROOT) -> tuple[str, str]:
        nonlocal resolver_calls
        if root != ROOT:
            fail("retained request snapshot selected another repository root")
        resolver_calls += 1
        return issuance_commit, issuance_tree

    request_module.__dict__["resolve_checkout_head"] = resolve_retained_checkout
    try:
        snapshot = load_snapshot(
            request["subject_cut"]["packet_commit"],
            issuance["authorized_ref"],
            issuance_commit_value=issuance_commit,
            live_currentness=False,
        )
    finally:
        request_module.__dict__["resolve_checkout_head"] = original_resolver
    if (
        resolver_calls != 1
        or snapshot.get("authorized_commit") != issuance_commit
        or snapshot.get("authorized_tree") != issuance_tree
    ):
        fail("retained request self-test escaped its issuance cut")
    return snapshot


def run_retained_request_self_test(
    request: dict[str, Any], snapshots: dict[str, bytes]
) -> None:
    helper_name = "immutable_git"
    request_module_name = "_ncp_b01_exact_review_request"
    prior_helper = sys.modules.get(helper_name)
    prior_request_module = sys.modules.get(request_module_name)
    helper = types.ModuleType(helper_name)
    helper.__file__ = str(ROOT / IMMUTABLE_GIT_RELATIVE)
    request_module = types.ModuleType(request_module_name)
    request_module.__file__ = str(ROOT / REQUEST_GENERATOR_RELATIVE)
    sys.modules[helper_name] = helper
    sys.modules[request_module_name] = request_module
    try:
        helper_code = compile(
            snapshots[IMMUTABLE_GIT_RELATIVE].decode("utf-8", errors="strict"),
            IMMUTABLE_GIT_RELATIVE,
            "exec",
            dont_inherit=True,
            optimize=0,
        )
        exec(helper_code, helper.__dict__)  # noqa: S102 - exact request-bound bytes
        request_code = compile(
            snapshots[REQUEST_GENERATOR_RELATIVE].decode("utf-8", errors="strict"),
            REQUEST_GENERATOR_RELATIVE,
            "exec",
            dont_inherit=True,
            optimize=0,
        )
        exec(  # noqa: S102 - exact request-bound bytes
            request_code,
            request_module.__dict__,
        )
        current_tool_identity = request_module.__dict__.get("current_tool_identity")
        request_self_test = request_module.__dict__.get("self_test")
        if not all(
            callable(function)
            for function in (
                current_tool_identity,
                request_self_test,
            )
        ):
            fail("exact retained request generator lacks its self-test API")

        subject_cut = request["subject_cut"]
        issuance = subject_cut["issuance_currentness"]
        snapshot = load_retained_request_snapshot(request_module, request)
        tool_identity = current_tool_identity(issuance["resolved_commit"], root=ROOT)
        if tool_identity != request["generated_by"]:
            fail("retained request self-test tool identity changed")
        request_self_test(snapshot, tool_identity)
    except ReviewerKitError:
        raise
    except (
        AssertionError,
        AttributeError,
        KeyError,
        MemoryError,
        OSError,
        RuntimeError,
        SyntaxError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as error:
        fail(f"retained B01 request self-test failed: {error}")
    finally:
        if prior_request_module is None:
            del sys.modules[request_module_name]
        else:
            sys.modules[request_module_name] = prior_request_module
        if prior_helper is None:
            del sys.modules[helper_name]
        else:
            sys.modules[helper_name] = prior_helper


def build_kit() -> dict[str, Any]:
    snapshots = snapshot_inputs()
    kit = build_kit_from_snapshots(snapshots)
    request = parse_object(
        snapshots[REQUEST_RELATIVE], REQUEST_RELATIVE, MAX_REQUEST_BYTES
    )
    validate_retained_issuance(request, snapshots)
    if snapshot_inputs() != snapshots:
        fail("reviewer-kit inputs changed during generation")
    return kit


def validate_kit(kit: dict[str, Any], schema: dict[str, Any]) -> None:
    try:
        validate_native_json_tree(
            kit,
            limits=json_limits(MAX_KIT_BYTES),
            label="generated reviewer kit",
        )
    except BoundedJsonError as error:
        fail(str(error))
    schema_validate(schema, kit, "B01 reviewer kit", KIT_SCHEMA_ID)
    if (
        kit.get("normative") is not False
        or kit.get("authorizing") is not False
        or kit.get("claim_boundary") != KIT_CLAIM_BOUNDARY
    ):
        fail("reviewer kit overclaims authority")
    contract = kit.get("materialization_contract")
    if contract != {
        "response_selector": "slot_id",
        "machine_injected_source_members": list(MACHINE_MEMBERS),
        "human_response_members": list(HUMAN_MEMBERS),
        "derived_member_forbidden": True,
        "registry_mutation": False,
        "output": "STDOUT_ONLY_STRUCTURAL_CANDIDATE",
        "output_schema": CANDIDATE_SCHEMA,
        "claim_boundary": MATERIALIZATION_CLAIM_BOUNDARY,
    }:
        fail("reviewer kit materialization boundary changed")
    forbidden_fields = {
        "review_id",
        "reviewer",
        "decision",
        "conditions",
        "role_authorization",
        "independence_assessment",
        "external_receipt",
        "timestamp_utc",
        "supersedes",
        "derived",
        "state",
        "status",
    }
    for collection_name in ("decisions", "slots"):
        stack: list[Any] = [kit[collection_name]]
        while stack:
            value = stack.pop()
            if type(value) is dict:
                forbidden = set(value) & forbidden_fields
                if forbidden:
                    fail(
                        f"reviewer kit {collection_name} contains response fields: "
                        f"{sorted(forbidden)}"
                    )
                stack.extend(value.values())
            elif type(value) is list:
                stack.extend(value)


def load_response(path: Path) -> dict[str, Any]:
    try:
        raw = read_bounded_regular_file(
            path,
            limits=FileSnapshotLimits(
                minimum_bytes=1,
                maximum_bytes=MAX_RESPONSE_BYTES,
            ),
            label=str(path),
        )
    except BoundedJsonError as error:
        fail(str(error))
    return parse_object(raw, str(path), MAX_RESPONSE_BYTES)


def execute_exact_registry_generator(
    source_bytes: bytes,
    candidate: dict[str, Any],
    *,
    artifact_overrides: dict[str, bytes] | None,
) -> tuple[dict[str, Any], bytes]:
    try:
        source_text = source_bytes.decode("utf-8", errors="strict")
        code = compile(
            source_text,
            REGISTRY_GENERATOR_RELATIVE,
            "exec",
            dont_inherit=True,
            optimize=0,
        )
        module = types.ModuleType("_ncp_b01_exact_decision_registry")
        module.__file__ = str(ROOT / REGISTRY_GENERATOR_RELATIVE)
        exec(code, module.__dict__)  # noqa: S102 - exact hash-bound repository bytes
        build_registry = module.__dict__.get("build_registry")
        serialize_registry = module.__dict__.get("generated_bytes")
        if not callable(build_registry) or not callable(serialize_registry):
            fail("exact registry generator lacks its build or serialization API")
        generated = build_registry(
            candidate,
            artifact_overrides=artifact_overrides,
        )
        serialized = serialize_registry(generated)
    except (
        AttributeError,
        KeyError,
        MemoryError,
        OSError,
        RuntimeError,
        SyntaxError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as error:
        fail(f"review candidate failed exact registry validation: {error}")
    if type(generated) is not dict:
        fail("exact registry generator returned a non-object")
    validate_registry_serialized_bytes(serialized)
    return generated, serialized


def validate_registry_serialized_bytes(value: Any) -> None:
    if type(value) is not bytes or not 1 <= len(value) <= MAX_INPUT_BYTES:
        fail("exact registry generator returned invalid or over-budget bytes")


def review_capture_phase_value(
    source: dict[str, Any], generated: dict[str, Any]
) -> str:
    if (
        source.get("schema") != REGISTRY_SOURCE_SCHEMA
        or source.get("normative") is not False
        or source.get("task") != "B01"
    ):
        fail("current registry source changed its B01 coordination boundary")
    records = source.get("review_records")
    generated_records = generated.get("review_records")
    if (
        type(records) is not list
        or type(generated_records) is not list
        or len(records) > MAX_REVIEW_RECORDS
        or len(generated_records) != len(records)
    ):
        fail("current registry source has an invalid review-capture roster")
    source_ids = [record.get("review_id") for record in records if type(record) is dict]
    generated_ids = [
        record.get("review_id") for record in generated_records if type(record) is dict
    ]
    if (
        len(source_ids) != len(records)
        or len(generated_ids) != len(records)
        or source_ids != generated_ids
        or len(source_ids) != len(set(source_ids))
    ):
        fail("current registry source changed review identity ordering or uniqueness")
    return ZERO_REVIEW_ISSUANCE if not records else REVIEW_CAPTURE_ACTIVE


def validate_current_review_capture(kit: dict[str, Any]) -> str:
    snapshots = {
        REGISTRY_GENERATOR_RELATIVE: read_file(
            REGISTRY_GENERATOR_RELATIVE, MAX_INPUT_BYTES
        ),
        REGISTRY_SCHEMA_RELATIVE: read_file(REGISTRY_SCHEMA_RELATIVE, MAX_INPUT_BYTES),
        REGISTRY_SOURCE_RELATIVE: read_file(REGISTRY_SOURCE_RELATIVE, MAX_INPUT_BYTES),
        CURRENT_PROPOSED_REGISTRY_RELATIVE: read_file(
            CURRENT_PROPOSED_REGISTRY_RELATIVE, MAX_INPUT_BYTES
        ),
    }
    for key, relative in (
        ("decision_registry_generator", REGISTRY_GENERATOR_RELATIVE),
        ("decision_registry_schema", REGISTRY_SCHEMA_RELATIVE),
    ):
        if kit["inputs"][key] != identity(relative, snapshots[relative]):
            fail(f"review-capture input {relative} differs from the reviewer kit")
    source = parse_object(
        snapshots[REGISTRY_SOURCE_RELATIVE],
        REGISTRY_SOURCE_RELATIVE,
        MAX_INPUT_BYTES,
    )
    generated, serialized = execute_exact_registry_generator(
        snapshots[REGISTRY_GENERATOR_RELATIVE],
        source,
        artifact_overrides=None,
    )
    if serialized != snapshots[CURRENT_PROPOSED_REGISTRY_RELATIVE]:
        fail("current proposed registry differs from the exact generated source")
    phase = review_capture_phase_value(source, generated)
    if any(
        read_file(relative, input_limits(relative)) != raw
        for relative, raw in snapshots.items()
    ):
        fail("review-capture inputs changed during lifecycle validation")
    return phase


def materialize_response_value(
    response: dict[str, Any],
    kit: dict[str, Any],
    *,
    artifact_overrides: dict[str, bytes] | None = None,
    registry_source_override: bytes | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_bytes = (
        read_file(REGISTRY_SOURCE_RELATIVE, MAX_INPUT_BYTES)
        if registry_source_override is None
        else registry_source_override
    )
    if type(source_bytes) is not bytes or not 1 <= len(source_bytes) <= MAX_INPUT_BYTES:
        fail("review materialization source override is invalid")
    materialization_snapshots = {
        RESPONSE_SCHEMA_RELATIVE: read_file(RESPONSE_SCHEMA_RELATIVE, MAX_SCHEMA_BYTES),
        CANDIDATE_SCHEMA_RELATIVE: read_file(
            CANDIDATE_SCHEMA_RELATIVE, MAX_SCHEMA_BYTES
        ),
        REGISTRY_GENERATOR_RELATIVE: read_file(
            REGISTRY_GENERATOR_RELATIVE, MAX_INPUT_BYTES
        ),
        REGISTRY_SCHEMA_RELATIVE: read_file(REGISTRY_SCHEMA_RELATIVE, MAX_INPUT_BYTES),
        REGISTRY_SOURCE_RELATIVE: source_bytes,
    }
    for key, relative in (
        ("review_response_schema", RESPONSE_SCHEMA_RELATIVE),
        ("review_source_candidate_schema", CANDIDATE_SCHEMA_RELATIVE),
        ("decision_registry_generator", REGISTRY_GENERATOR_RELATIVE),
        ("decision_registry_schema", REGISTRY_SCHEMA_RELATIVE),
    ):
        if kit["inputs"][key] != identity(
            relative, materialization_snapshots[relative]
        ):
            fail(f"materialization input {relative} differs from the reviewer kit")
    response_schema = parse_object(
        materialization_snapshots[RESPONSE_SCHEMA_RELATIVE],
        RESPONSE_SCHEMA_RELATIVE,
        MAX_SCHEMA_BYTES,
    )
    schema_validate(
        response_schema, response, "B01 review response", RESPONSE_SCHEMA_ID
    )
    if response.get("schema") != RESPONSE_SCHEMA:
        fail("review response schema is not supported")
    slot_id = response["slot_id"]
    matching = [slot for slot in kit["slots"] if slot["slot_id"] == slot_id]
    if len(matching) != 1:
        fail("review response selects an unknown or duplicated slot")
    slot = matching[0]
    subjects = {
        decision["adr_id"]: decision["subject"] for decision in kit["decisions"]
    }
    record = {name: copy.deepcopy(response[name]) for name in HUMAN_MEMBERS}
    record.update(
        {
            "adr_id": slot["adr_id"],
            "role_id": slot["role_id"],
            "subject": copy.deepcopy(subjects[slot["adr_id"]]),
        }
    )
    record = {name: record[name] for name in EXPECTED_SOURCE_FIELDS}

    source = parse_object(
        materialization_snapshots[REGISTRY_SOURCE_RELATIVE],
        REGISTRY_SOURCE_RELATIVE,
        MAX_INPUT_BYTES,
    )
    records = source.get("review_records")
    if type(records) is not list or len(records) >= MAX_REVIEW_RECORDS:
        fail("decision-registry source cannot accept another bounded review record")
    candidate = copy.deepcopy(source)
    candidate["review_records"].append(record)
    generated, _serialized = execute_exact_registry_generator(
        materialization_snapshots[REGISTRY_GENERATOR_RELATIVE],
        candidate,
        artifact_overrides=artifact_overrides,
    )
    matches = [
        item
        for item in generated.get("review_records", [])
        if item.get("review_id") == record["review_id"]
    ]
    if len(matches) != 1:
        fail("frozen registry validation did not retain one candidate review")
    rejoin_snapshots = {
        relative: raw
        for relative, raw in materialization_snapshots.items()
        if registry_source_override is None or relative != REGISTRY_SOURCE_RELATIVE
    }
    if any(
        read_file(relative, input_limits(relative)) != raw
        for relative, raw in rejoin_snapshots.items()
    ):
        fail("review materialization inputs changed during validation")
    validation_context = {
        "reviewer_kit": identity(OUTPUT_RELATIVE, generated_bytes(kit)),
        "candidate_schema": identity(
            CANDIDATE_SCHEMA_RELATIVE,
            materialization_snapshots[CANDIDATE_SCHEMA_RELATIVE],
        ),
        "registry_generator": identity(
            REGISTRY_GENERATOR_RELATIVE,
            materialization_snapshots[REGISTRY_GENERATOR_RELATIVE],
        ),
        "validated_against_registry_source": identity(
            REGISTRY_SOURCE_RELATIVE,
            materialization_snapshots[REGISTRY_SOURCE_RELATIVE],
        ),
    }
    return record, validation_context


def require_retained_kit(kit: dict[str, Any], content: bytes) -> None:
    current = read_file(OUTPUT_RELATIVE, MAX_KIT_BYTES)
    if current != content:
        fail("generated reviewer kit is missing or stale")
    parsed = parse_object(current, OUTPUT_RELATIVE, MAX_KIT_BYTES)
    if parsed != kit:
        fail("generated reviewer kit semantics differ from expected content")


def materialize_response(path: Path, kit: dict[str, Any]) -> dict[str, Any]:
    response = load_response(path)
    record, validation_context = materialize_response_value(response, kit)
    candidate_schema_raw = read_file(CANDIDATE_SCHEMA_RELATIVE, MAX_SCHEMA_BYTES)
    if validation_context["candidate_schema"] != identity(
        CANDIDATE_SCHEMA_RELATIVE, candidate_schema_raw
    ):
        fail("candidate schema changed after registry validation")
    candidate_schema = parse_object(
        candidate_schema_raw,
        CANDIDATE_SCHEMA_RELATIVE,
        MAX_SCHEMA_BYTES,
    )
    envelope = source_candidate_envelope(
        response,
        record,
        kit,
        validation_context,
        candidate_schema,
    )
    if read_file(CANDIDATE_SCHEMA_RELATIVE, MAX_SCHEMA_BYTES) != candidate_schema_raw:
        fail("candidate schema changed during envelope validation")
    return envelope


def source_candidate_envelope(
    response: dict[str, Any],
    record: dict[str, Any],
    kit: dict[str, Any],
    validation_context: dict[str, Any],
    candidate_schema: dict[str, Any],
) -> dict[str, Any]:
    exact_keys(
        validation_context,
        {
            "reviewer_kit",
            "candidate_schema",
            "registry_generator",
            "validated_against_registry_source",
        },
        "review source candidate validation context",
    )
    if validation_context != {
        "reviewer_kit": identity(OUTPUT_RELATIVE, generated_bytes(kit)),
        "candidate_schema": copy.deepcopy(
            kit["inputs"]["review_source_candidate_schema"]
        ),
        "registry_generator": copy.deepcopy(
            kit["inputs"]["decision_registry_generator"]
        ),
        "validated_against_registry_source": validation_context[
            "validated_against_registry_source"
        ],
    }:
        fail("review source candidate validation context changed fixed identities")
    if validation_context["validated_against_registry_source"].get("path") != (
        REGISTRY_SOURCE_RELATIVE
    ):
        fail("review source candidate names another registry source")
    matching_slots = [
        slot for slot in kit["slots"] if slot["slot_id"] == response.get("slot_id")
    ]
    if len(matching_slots) != 1:
        fail("review source candidate does not select exactly one kit slot")
    slot = matching_slots[0]
    subjects = {
        decision["adr_id"]: decision["subject"] for decision in kit["decisions"]
    }
    if any(record.get(name) != response.get(name) for name in HUMAN_MEMBERS):
        fail("review source candidate changed human-supplied fields")
    if (
        record.get("adr_id") != slot["adr_id"]
        or record.get("role_id") != slot["role_id"]
        or record.get("subject") != subjects.get(slot["adr_id"])
    ):
        fail("review source candidate changed machine-owned fields")
    envelope = {
        "schema": CANDIDATE_SCHEMA,
        "normative": False,
        "authorizing": False,
        "claim_boundary": CANDIDATE_CLAIM_BOUNDARY,
        "slot_id": response["slot_id"],
        "validation_context": copy.deepcopy(validation_context),
        "registry_mutation": False,
        "external_verifier_required": True,
        "source_record": copy.deepcopy(record),
    }
    exact_keys(
        envelope,
        {
            "schema",
            "normative",
            "authorizing",
            "claim_boundary",
            "slot_id",
            "validation_context",
            "registry_mutation",
            "external_verifier_required",
            "source_record",
        },
        "review source candidate",
    )
    if (
        envelope["normative"] is not False
        or envelope["authorizing"] is not False
        or envelope["registry_mutation"] is not False
        or envelope["external_verifier_required"] is not True
        or envelope["claim_boundary"] != CANDIDATE_CLAIM_BOUNDARY
        or set(envelope["source_record"]) != set(EXPECTED_SOURCE_FIELDS)
    ):
        fail("review source candidate overclaims authority or changes shape")
    schema_validate(
        candidate_schema,
        envelope,
        "B01 review source candidate",
        CANDIDATE_SCHEMA_ID,
    )
    return envelope


def slot_envelope(slot_id: str, kit: dict[str, Any]) -> dict[str, Any]:
    if SLOT_ID.fullmatch(slot_id) is None:
        fail("slot ID is not canonical")
    matching = [slot for slot in kit["slots"] if slot["slot_id"] == slot_id]
    if len(matching) != 1:
        fail("slot ID is not in the retained request")
    slot = copy.deepcopy(matching[0])
    subjects = {
        decision["adr_id"]: decision["subject"] for decision in kit["decisions"]
    }
    return {
        "schema": "ncp.b01-review-slot-envelope.v1",
        "normative": False,
        "authorizing": False,
        "claim_boundary": KIT_CLAIM_BOUNDARY,
        "slot": slot,
        "machine_injected_source": {
            "adr_id": slot["adr_id"],
            "role_id": slot["role_id"],
            "subject": copy.deepcopy(subjects[slot["adr_id"]]),
        },
        "human_response_schema": copy.deepcopy(kit["inputs"]["review_response_schema"]),
    }


def must_fail(action: Any, label: str) -> None:
    try:
        action()
    except ReviewerKitError:
        return
    fail(f"hostile reviewer-kit self-test unexpectedly passed: {label}")


def self_test() -> None:
    snapshots = snapshot_inputs()
    kit = build_kit_from_snapshots(snapshots)
    request = parse_object(
        snapshots[REQUEST_RELATIVE], REQUEST_RELATIVE, MAX_REQUEST_BYTES
    )
    hostile_current_checkout_called = False
    hostile_request_module = types.ModuleType("_ncp_b01_hostile_current_checkout")

    def hostile_current_checkout(*, root: Path = ROOT) -> tuple[str, str]:
        nonlocal hostile_current_checkout_called
        hostile_current_checkout_called = True
        return "f" * 40, "e" * 40

    def synthetic_request_load_snapshot(
        _packet_commit: str,
        _authorized_ref: str,
        *,
        issuance_commit_value: str | None,
        live_currentness: bool,
    ) -> dict[str, Any]:
        if issuance_commit_value is None or live_currentness:
            fail("synthetic retained snapshot changed its mode")
        commit, tree = hostile_request_module.resolve_checkout_head(root=ROOT)
        return {"authorized_commit": commit, "authorized_tree": tree}

    hostile_request_module.resolve_checkout_head = hostile_current_checkout
    hostile_request_module.load_snapshot = synthetic_request_load_snapshot
    retained_probe = load_retained_request_snapshot(hostile_request_module, request)
    if (
        hostile_current_checkout_called
        or retained_probe["authorized_commit"]
        != request["subject_cut"]["issuance_currentness"]["resolved_commit"]
    ):
        fail("current checkout leaked into retained request self-test")
    injected_immutable_git = types.ModuleType("immutable_git")
    injected_immutable_git.require_ancestor = lambda *_args, **_kwargs: None
    prior_immutable_git = sys.modules.get("immutable_git")
    sys.modules["immutable_git"] = injected_immutable_git
    try:
        validate_retained_issuance(request, snapshots)
    finally:
        if prior_immutable_git is None:
            del sys.modules["immutable_git"]
        else:
            sys.modules["immutable_git"] = prior_immutable_git
    run_retained_request_self_test(request, snapshots)
    current_phase = validate_current_review_capture(kit)
    if current_phase not in (ZERO_REVIEW_ISSUANCE, REVIEW_CAPTURE_ACTIVE):
        fail("current review source selected an unknown lifecycle phase")
    isolated_zero_source = parse_object(
        read_file(REGISTRY_SOURCE_RELATIVE, MAX_INPUT_BYTES),
        REGISTRY_SOURCE_RELATIVE,
        MAX_INPUT_BYTES,
    )
    isolated_zero_source["review_records"] = []
    isolated_zero_source_bytes = generated_bytes(isolated_zero_source)
    isolated_zero_generated, _isolated_zero_registry_bytes = (
        execute_exact_registry_generator(
            snapshots[REGISTRY_GENERATOR_RELATIVE],
            isolated_zero_source,
            artifact_overrides=None,
        )
    )
    if (
        review_capture_phase_value(isolated_zero_source, isolated_zero_generated)
        != ZERO_REVIEW_ISSUANCE
    ):
        fail("isolated zero-review source selected another lifecycle phase")
    maximum_phase_source = {
        "schema": REGISTRY_SOURCE_SCHEMA,
        "normative": False,
        "task": "B01",
        "review_records": [
            {"review_id": f"boundary-review-{index:03d}"}
            for index in range(MAX_REVIEW_RECORDS)
        ],
    }
    maximum_phase_generated = {
        "review_records": copy.deepcopy(maximum_phase_source["review_records"])
    }
    if (
        review_capture_phase_value(maximum_phase_source, maximum_phase_generated)
        != REVIEW_CAPTURE_ACTIVE
    ):
        fail("maximum review-capture roster selected another lifecycle phase")
    overflow_phase_source = copy.deepcopy(maximum_phase_source)
    overflow_phase_source["review_records"].append(
        {"review_id": "boundary-review-overflow"}
    )
    must_fail(
        lambda: review_capture_phase_value(
            overflow_phase_source,
            maximum_phase_generated,
        ),
        "review-capture roster above 256 records",
    )
    validate_registry_serialized_bytes(
        b'{"payload":"' + b"x" * (MAX_KIT_BYTES + 1) + b'"}\n'
    )
    must_fail(
        lambda: validate_registry_serialized_bytes(b"x" * (MAX_INPUT_BYTES + 1)),
        "registry serialization above two MiB",
    )
    kit_schema = parse_object(
        snapshots[KIT_SCHEMA_RELATIVE], KIT_SCHEMA_RELATIVE, MAX_SCHEMA_BYTES
    )
    response_schema = parse_object(
        snapshots[RESPONSE_SCHEMA_RELATIVE], RESPONSE_SCHEMA_RELATIVE, MAX_SCHEMA_BYTES
    )
    candidate_schema = parse_object(
        snapshots[CANDIDATE_SCHEMA_RELATIVE],
        CANDIDATE_SCHEMA_RELATIVE,
        MAX_SCHEMA_BYTES,
    )
    if generated_bytes(kit) != generated_bytes(build_kit_from_snapshots(snapshots)):
        fail("reviewer-kit generation is not deterministic")

    evolved_registry_snapshots = copy.deepcopy(snapshots)
    evolved_registry_snapshots["docs/adr/decision-registry.proposed.v1.json"] = (
        b'{"review_records":[{"review_id":"later-authentic-review"}]}\n'
    )
    evolved_registry_kit = build_kit_from_snapshots(evolved_registry_snapshots)
    if generated_bytes(evolved_registry_kit) != generated_bytes(kit):
        fail("live proposed-registry evolution changed the frozen reviewer kit")

    hostile_snapshots = copy.deepcopy(snapshots)
    hostile_snapshots[REQUEST_RELATIVE] = b'{"schema":'
    must_fail(
        lambda: build_kit_from_snapshots(hostile_snapshots),
        "malformed exact request bytes",
    )

    hostile = copy.deepcopy(kit)
    hostile["authorizing"] = True
    must_fail(lambda: validate_kit(hostile, kit_schema), "authorizing kit")
    hostile = copy.deepcopy(kit)
    hostile["slots"][0]["decision"] = "ACCEPT"
    must_fail(lambda: validate_kit(hostile, kit_schema), "prefilled decision")
    hostile = copy.deepcopy(kit)
    hostile["slots"][0]["reviewer"] = {"identity": "model:forbidden"}
    must_fail(lambda: validate_kit(hostile, kit_schema), "prefilled reviewer")

    hostile_snapshots = copy.deepcopy(snapshots)
    request = parse_object(
        hostile_snapshots[REQUEST_RELATIVE], REQUEST_RELATIVE, MAX_REQUEST_BYTES
    )
    request["review_slots"][0]["state"] = "FILLED"
    hostile_snapshots[REQUEST_RELATIVE] = generated_bytes(request)
    must_fail(
        lambda: build_kit_from_snapshots(hostile_snapshots),
        "filled request slot",
    )
    hostile_snapshots = copy.deepcopy(snapshots)
    request = parse_object(
        hostile_snapshots[REQUEST_RELATIVE], REQUEST_RELATIVE, MAX_REQUEST_BYTES
    )
    request["review_slots"][1]["slot_id"] = request["review_slots"][0]["slot_id"]
    hostile_snapshots[REQUEST_RELATIVE] = generated_bytes(request)
    must_fail(
        lambda: build_kit_from_snapshots(hostile_snapshots),
        "duplicate request slot",
    )
    hostile_snapshots = copy.deepcopy(snapshots)
    request = parse_object(
        hostile_snapshots[REQUEST_RELATIVE], REQUEST_RELATIVE, MAX_REQUEST_BYTES
    )
    request["review_slots"][0]["subject"]["decision_set_sha256"] = "0" * 64
    hostile_snapshots[REQUEST_RELATIVE] = generated_bytes(request)
    must_fail(
        lambda: build_kit_from_snapshots(hostile_snapshots),
        "stale decision set",
    )
    for label, mutate in (
        (
            "substituted role label",
            lambda value: value["review_slots"][0].__setitem__(
                "role_label", "attacker role"
            ),
        ),
        (
            "substituted identity group",
            lambda value: value["review_slots"][0].__setitem__(
                "distinct_identity_group", "adr-001.attacker-role"
            ),
        ),
        (
            "substituted identity ordinal",
            lambda value: value["review_slots"][0].__setitem__("identity_ordinal", 2),
        ),
        (
            "substituted claim boundary",
            lambda value: value.__setitem__("claim_boundary", "ATTACKER_BOUNDARY"),
        ),
        (
            "substituted issuance currentness",
            lambda value: value["subject_cut"]["issuance_currentness"].__setitem__(
                "resolved_commit", "0" * 40
            ),
        ),
    ):
        hostile_snapshots = copy.deepcopy(snapshots)
        request = parse_object(
            hostile_snapshots[REQUEST_RELATIVE], REQUEST_RELATIVE, MAX_REQUEST_BYTES
        )
        mutate(request)
        hostile_snapshots[REQUEST_RELATIVE] = generated_bytes(request)
        must_fail(
            lambda value=hostile_snapshots: build_kit_from_snapshots(value),
            label,
        )
    must_fail(
        lambda: parse_object(b'{"x":1,"x":2}', "duplicate JSON", 128),
        "duplicate JSON key",
    )
    must_fail(
        lambda: parse_object(b'{"x":1.0}', "floating JSON", 128),
        "floating JSON number",
    )

    response_fixture = {
        "schema": RESPONSE_SCHEMA,
        "slot_id": kit["slots"][0]["slot_id"],
        "review_id": "reviewer-supplied-id",
        "reviewer": {
            "identity": "urn:example:human-reviewer",
            "identity_kind": "PERSON",
            "independence_claimed": False,
            "implementation_owner_identities": ["urn:example:ncp-owner"],
        },
        "decision": "REJECT",
        "conditions": [],
        "role_authorization": {
            "url": "https://review.example/role/one",
            "path": "evidence/implementation/reviews/B01/role-one.json",
            "sha256": "1" * 64,
            "bytes": 1,
            "media_type": "application/json",
        },
        "independence_assessment": None,
        "external_receipt": {
            "url": "https://review.example/receipt/one",
            "path": "evidence/implementation/reviews/B01/receipt-one.json",
            "sha256": "2" * 64,
            "bytes": 1,
            "media_type": "application/json",
        },
        "timestamp_utc": "2026-08-31T12:00:00Z",
        "supersedes": None,
    }
    role_bytes = b'{"kind":"role-authorization"}\n'
    receipt_bytes = b'{"kind":"external-review-receipt"}\n'
    response_fixture["role_authorization"]["sha256"] = sha256(role_bytes)
    response_fixture["role_authorization"]["bytes"] = len(role_bytes)
    response_fixture["external_receipt"]["sha256"] = sha256(receipt_bytes)
    response_fixture["external_receipt"]["bytes"] = len(receipt_bytes)
    schema_validate(
        response_schema,
        response_fixture,
        "self-test review response",
        RESPONSE_SCHEMA_ID,
    )
    must_fail(
        lambda: materialize_response_value(
            response_fixture,
            kit,
            artifact_overrides={
                response_fixture["role_authorization"]["path"]: role_bytes,
                response_fixture["external_receipt"]["path"]: receipt_bytes,
            },
            registry_source_override=generated_bytes(maximum_phase_source),
        ),
        "257th bounded review materialization",
    )
    injected_module = types.ModuleType("generate_decision_registry")
    injected_module.build_registry = lambda *_args, **_kwargs: {"review_records": []}
    prior_module = sys.modules.get("generate_decision_registry")
    sys.modules["generate_decision_registry"] = injected_module
    try:
        candidate, candidate_context = materialize_response_value(
            response_fixture,
            evolved_registry_kit,
            artifact_overrides={
                response_fixture["role_authorization"]["path"]: role_bytes,
                response_fixture["external_receipt"]["path"]: receipt_bytes,
            },
            registry_source_override=isolated_zero_source_bytes,
        )
    finally:
        if prior_module is None:
            del sys.modules["generate_decision_registry"]
        else:
            sys.modules["generate_decision_registry"] = prior_module
    if (
        set(candidate) != set(EXPECTED_SOURCE_FIELDS)
        or candidate["adr_id"] != evolved_registry_kit["slots"][0]["adr_id"]
        or candidate["role_id"] != evolved_registry_kit["slots"][0]["role_id"]
        or candidate["subject"] != evolved_registry_kit["decisions"][0]["subject"]
    ):
        fail("positive response materialization changed machine-owned fields")
    one_record_source = copy.deepcopy(isolated_zero_source)
    one_record_source["review_records"].append(copy.deepcopy(candidate))
    one_record_generated, _one_record_bytes = execute_exact_registry_generator(
        snapshots[REGISTRY_GENERATOR_RELATIVE],
        one_record_source,
        artifact_overrides={
            response_fixture["role_authorization"]["path"]: role_bytes,
            response_fixture["external_receipt"]["path"]: receipt_bytes,
        },
    )
    if (
        review_capture_phase_value(one_record_source, one_record_generated)
        != REVIEW_CAPTURE_ACTIVE
    ):
        fail("one valid review did not activate the review-capture phase")
    hostile_phase_source = copy.deepcopy(one_record_source)
    hostile_phase_source["review_records"] = "REVIEW_CAPTURE_ACTIVE"
    must_fail(
        lambda: review_capture_phase_value(
            hostile_phase_source,
            one_record_generated,
        ),
        "caller-forced review-capture phase",
    )
    hostile_phase_generated = copy.deepcopy(one_record_generated)
    hostile_phase_generated["review_records"] = []
    must_fail(
        lambda: review_capture_phase_value(
            one_record_source,
            hostile_phase_generated,
        ),
        "review-capture source/output mismatch",
    )
    envelope = source_candidate_envelope(
        response_fixture,
        candidate,
        kit,
        candidate_context,
        candidate_schema,
    )
    if (
        envelope["schema"] != CANDIDATE_SCHEMA
        or envelope["authorizing"] is not False
        or envelope["external_verifier_required"] is not True
        or envelope["source_record"] != candidate
    ):
        fail("source candidate envelope changed its non-authorizing boundary")
    for label, field, value in (
        ("normative candidate", "normative", True),
        ("authorizing candidate", "authorizing", True),
        ("mutating candidate", "registry_mutation", True),
        ("verifier-optional candidate", "external_verifier_required", False),
        ("candidate claim drift", "claim_boundary", "ATTACKER_BOUNDARY"),
    ):
        hostile_envelope = copy.deepcopy(envelope)
        hostile_envelope[field] = value
        must_fail(
            lambda value=hostile_envelope: schema_validate(
                candidate_schema,
                value,
                label,
                CANDIDATE_SCHEMA_ID,
            ),
            label,
        )
    hostile_envelope = copy.deepcopy(envelope)
    hostile_envelope["attacker_field"] = True
    must_fail(
        lambda: schema_validate(
            candidate_schema,
            hostile_envelope,
            "candidate extra field",
            CANDIDATE_SCHEMA_ID,
        ),
        "candidate extra field",
    )
    for context_name in ("reviewer_kit", "candidate_schema", "registry_generator"):
        hostile_context = copy.deepcopy(candidate_context)
        hostile_context[context_name]["sha256"] = "0" * 64
        must_fail(
            lambda value=hostile_context: source_candidate_envelope(
                response_fixture,
                candidate,
                kit,
                value,
                candidate_schema,
            ),
            f"candidate {context_name} identity drift",
        )
    hostile_context = copy.deepcopy(candidate_context)
    hostile_context["validated_against_registry_source"]["path"] = (
        "docs/adr/attacker-source.json"
    )
    must_fail(
        lambda: source_candidate_envelope(
            response_fixture,
            candidate,
            kit,
            hostile_context,
            candidate_schema,
        ),
        "candidate registry-source identity drift",
    )
    hostile_response = copy.deepcopy(response_fixture)
    hostile_response["slot_id"] = "adr-011.attacker-role.99"
    must_fail(
        lambda: source_candidate_envelope(
            hostile_response,
            candidate,
            kit,
            candidate_context,
            candidate_schema,
        ),
        "candidate unknown slot",
    )
    hostile_record = copy.deepcopy(candidate)
    hostile_record["review_id"] = "attacker-substitution"
    must_fail(
        lambda: source_candidate_envelope(
            response_fixture,
            hostile_record,
            kit,
            candidate_context,
            candidate_schema,
        ),
        "candidate human-field substitution",
    )
    hostile_record = copy.deepcopy(candidate)
    hostile_record["role_id"] = "attacker-role"
    must_fail(
        lambda: source_candidate_envelope(
            response_fixture,
            hostile_record,
            kit,
            candidate_context,
            candidate_schema,
        ),
        "candidate machine-field substitution",
    )

    original_read_file = globals()["read_file"]
    source_read_count = 0

    def unstable_read_file(relative: str, maximum_bytes: int) -> bytes:
        nonlocal source_read_count
        raw = original_read_file(relative, maximum_bytes)
        if relative == REGISTRY_SOURCE_RELATIVE:
            source_read_count += 1
            raw = isolated_zero_source_bytes
            if source_read_count > 1:
                return raw + b" "
        return raw

    globals()["read_file"] = unstable_read_file
    try:
        must_fail(
            lambda: materialize_response_value(
                response_fixture,
                kit,
                artifact_overrides={
                    response_fixture["role_authorization"]["path"]: role_bytes,
                    response_fixture["external_receipt"]["path"]: receipt_bytes,
                },
            ),
            "registry source changed during materialization",
        )
    finally:
        globals()["read_file"] = original_read_file

    duplicate_source = copy.deepcopy(isolated_zero_source)
    duplicate_source["review_records"].extend(
        [copy.deepcopy(candidate), copy.deepcopy(candidate)]
    )
    must_fail(
        lambda: execute_exact_registry_generator(
            snapshots[REGISTRY_GENERATOR_RELATIVE],
            duplicate_source,
            artifact_overrides={
                response_fixture["role_authorization"]["path"]: role_bytes,
                response_fixture["external_receipt"]["path"]: receipt_bytes,
            },
        ),
        "duplicate review candidate",
    )
    hostile_response = copy.deepcopy(response_fixture)
    hostile_response["review_id"] = "invalid-supersession-candidate"
    hostile_response["supersedes"] = "missing-prior-review"
    must_fail(
        lambda: materialize_response_value(
            hostile_response,
            kit,
            artifact_overrides={
                hostile_response["role_authorization"]["path"]: role_bytes,
                hostile_response["external_receipt"]["path"]: receipt_bytes,
            },
            registry_source_override=isolated_zero_source_bytes,
        ),
        "unknown review supersession",
    )
    independent_fixture = copy.deepcopy(response_fixture)
    independent_slot = next(
        slot for slot in kit["slots"] if slot["requires_independence"]
    )
    independent_fixture["slot_id"] = independent_slot["slot_id"]
    independent_fixture["review_id"] = "honest-nonindependent-rejection"
    nonqualifying, _ = materialize_response_value(
        independent_fixture,
        kit,
        artifact_overrides={
            independent_fixture["role_authorization"]["path"]: role_bytes,
            independent_fixture["external_receipt"]["path"]: receipt_bytes,
        },
        registry_source_override=isolated_zero_source_bytes,
    )
    if (
        nonqualifying["adr_id"] != independent_slot["adr_id"]
        or nonqualifying["role_id"] != independent_slot["role_id"]
        or nonqualifying["reviewer"]["independence_claimed"] is not False
        or nonqualifying["independence_assessment"] is not None
    ):
        fail("honest non-independent response changed during materialization")
    independent_fixture["review_id"] = "honest-nonqualifying-acceptance"
    independent_fixture["decision"] = "ACCEPT"
    materialize_response_value(
        independent_fixture,
        kit,
        artifact_overrides={
            independent_fixture["role_authorization"]["path"]: role_bytes,
            independent_fixture["external_receipt"]["path"]: receipt_bytes,
        },
        registry_source_override=isolated_zero_source_bytes,
    )
    assessment_bytes = b'{"kind":"independence-assessment"}\n'
    qualifying_fixture = copy.deepcopy(independent_fixture)
    qualifying_fixture["review_id"] = "structurally-qualifying-independent-acceptance"
    qualifying_fixture["reviewer"]["independence_claimed"] = True
    qualifying_fixture["independence_assessment"] = {
        "url": "https://review.example/independence/one",
        "path": "evidence/implementation/reviews/B01/independence-one.json",
        "sha256": sha256(assessment_bytes),
        "bytes": len(assessment_bytes),
        "media_type": "application/json",
    }
    qualifying, _ = materialize_response_value(
        qualifying_fixture,
        kit,
        artifact_overrides={
            qualifying_fixture["role_authorization"]["path"]: role_bytes,
            qualifying_fixture["external_receipt"]["path"]: receipt_bytes,
            qualifying_fixture["independence_assessment"]["path"]: assessment_bytes,
        },
        registry_source_override=isolated_zero_source_bytes,
    )
    if (
        qualifying["decision"] != "ACCEPT"
        or qualifying["reviewer"]["independence_claimed"] is not True
        or qualifying["independence_assessment"] is None
    ):
        fail("independent positive response changed during materialization")
    hostile_response = copy.deepcopy(response_fixture)
    hostile_response["adr_id"] = "ADR-001"
    must_fail(
        lambda: schema_validate(
            response_schema,
            hostile_response,
            "hostile machine-field override",
            RESPONSE_SCHEMA_ID,
        ),
        "response machine-field override",
    )
    hostile_response = copy.deepcopy(response_fixture)
    hostile_response["role_authorization"]["path"] = (
        "evidence/implementation/reviews/B01/../escaped.json"
    )
    must_fail(
        lambda: schema_validate(
            response_schema,
            hostile_response,
            "hostile immediate parent path",
            RESPONSE_SCHEMA_ID,
        ),
        "response immediate parent path",
    )
    hostile_response = copy.deepcopy(response_fixture)
    hostile_response["decision"] = "ACCEPT_WITH_CONDITIONS"
    must_fail(
        lambda: schema_validate(
            response_schema,
            hostile_response,
            "hostile empty conditional response",
            RESPONSE_SCHEMA_ID,
        ),
        "conditional response without conditions",
    )


def print_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--write", action="store_true", help="replace the generated kit")
    modes.add_argument("--check", action="store_true", help="check the kit (default)")
    modes.add_argument(
        "--list", action="store_true", help="list the fixed slots as TSV"
    )
    modes.add_argument("--slot", metavar="SLOT_ID", help="emit one machine-only slot")
    modes.add_argument(
        "--materialize-response",
        metavar="PATH",
        type=Path,
        help="validate one completed human response and emit a source candidate",
    )
    parser.add_argument("--self-test", action="store_true", help="run hostile controls")
    args = parser.parse_args()

    try:
        if args.self_test:
            self_test()
        kit = build_kit()
        content = generated_bytes(kit)
        if not args.write:
            require_retained_kit(kit, content)
        review_capture_phase = validate_current_review_capture(kit)
        if args.list:
            print(
                "slot_id\tadr_id\trole_id\trequires_independence\t"
                "identity_ordinal\trole_label"
            )
            for slot in kit["slots"]:
                print(
                    f"{slot['slot_id']}\t{slot['adr_id']}\t{slot['role_id']}\t"
                    f"{str(slot['requires_independence']).lower()}\t"
                    f"{slot['identity_ordinal']}\t{slot['role_label']}"
                )
            return 0
        if args.slot is not None:
            print_json(slot_envelope(args.slot, kit))
            return 0
        if args.materialize_response is not None:
            candidate = materialize_response(args.materialize_response, kit)
            print(
                "STRUCTURAL CANDIDATE ONLY — no authorship, role, independence, "
                "ADR, task, protocol, or release authority",
                file=sys.stderr,
            )
            print_json(candidate)
            return 0
        if args.write:
            try:
                from selector_closure_codec import atomic_write_regular_file

                atomic_write_regular_file(
                    ROOT / OUTPUT_RELATIVE,
                    content,
                    label="B01 reviewer-kit output",
                )
            except (ImportError, OSError, RuntimeError, ValueError) as error:
                fail(f"cannot install reviewer kit: {error}")
            if read_file(OUTPUT_RELATIVE, MAX_KIT_BYTES) != content:
                fail("installed reviewer kit differs from generated bytes")
            print(f"WROTE {OUTPUT_RELATIVE}")
            return 0
        print(
            f"OK B01 reviewer kit: {review_capture_phase}; 53 machine-bound "
            "slots; no review, ADR, task, protocol, or release authority"
        )
        return 0
    except (OSError, ReviewerKitError) as error:
        print(f"ERROR B01 reviewer kit: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
