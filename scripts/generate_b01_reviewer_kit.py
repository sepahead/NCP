#!/usr/bin/env python3
"""Generate the non-authorizing B01 reviewer preparation kit.

The kit copies immutable machine facts from the retained review request. It
never emits a reviewer identity, decision, timestamp, evidence reference, or
task transition. Structural materialization helpers support the separate
private-bundle preflight. This generator does not admit or mutate a review.
"""

from __future__ import annotations

# Disable bytecode before any import can resolve a repository module.
# ruff: noqa: E402, I001
import sys

sys.dont_write_bytecode = True

import argparse
import copy
import hashlib
import json
import os
import re
import tempfile
import types
from pathlib import Path, PurePosixPath
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
PREFLIGHT_RELATIVE = "scripts/preflight_b01_review_bundle.py"
BOUNDED_JSON_RELATIVE = "scripts/bounded_json.py"
SCHEMA_VALIDATOR_RELATIVE = "scripts/validate_evidence_schemas.py"
REQUEST_RELATIVE = "evidence/implementation/requests/B01/review-request.v1.json"
REQUEST_GENERATOR_RELATIVE = "scripts/generate_b01_review_request.py"
IMMUTABLE_GIT_RELATIVE = "scripts/immutable_git.py"
KIT_SCHEMA_RELATIVE = "evidence/implementation/requests/B01/reviewer-kit.schema.v2.json"
RESPONSE_SCHEMA_RELATIVE = (
    "evidence/implementation/requests/B01/review-response.schema.v2.json"
)
CANDIDATE_SCHEMA_RELATIVE = (
    "evidence/implementation/requests/B01/review-source-candidate.schema.v2.json"
)
OUTPUT_RELATIVE = "evidence/implementation/requests/B01/reviewer-kit.v2.json"
REGISTRY_GENERATOR_RELATIVE = "scripts/generate_decision_registry.py"
REGISTRY_SCHEMA_RELATIVE = "docs/adr/decision-registry.proposed.schema.v1.json"
CURRENT_PROPOSED_REGISTRY_RELATIVE = "docs/adr/decision-registry.proposed.v1.json"
REGISTRY_SOURCE_RELATIVE = "docs/adr/decision-registry.source.v1.json"
REVIEW_PACKET_RELATIVE = "docs/adr/B01_REVIEW_PACKET.md"
CLOSURE_SOURCE_RELATIVE = "docs/adr/decision-closure.source.v1.json"
CLOSURE_SCHEMA_RELATIVE = "docs/adr/decision-closure.source.schema.v1.json"
SEMANTIC_CORPUS_RELATIVE = (
    "prototypes/b01-architecture-evidence/adr-example-semantics/corpus.v1.json"
)
PROMOTION_TARGET_RELATIVE = "contract/decision-registry.v1.json"
FIXED_REGISTRY_REPLAY_PATHS = (
    REGISTRY_GENERATOR_RELATIVE,
    REGISTRY_SCHEMA_RELATIVE,
    CLOSURE_SOURCE_RELATIVE,
    CLOSURE_SCHEMA_RELATIVE,
    REVIEW_PACKET_RELATIVE,
    SEMANTIC_CORPUS_RELATIVE,
)

KIT_SCHEMA = "ncp.b01-reviewer-kit.v2"
RESPONSE_SCHEMA = "ncp.b01-review-response.v2"
CANDIDATE_SCHEMA = "ncp.b01-review-source-candidate.v2"
SLOT_ENVELOPE_SCHEMA = "ncp.b01-review-slot-envelope.v2"
KIT_SCHEMA_ID = "https://sepahead.github.io/NCP/schemas/b01-reviewer-kit.v2.json"
RESPONSE_SCHEMA_ID = (
    "https://sepahead.github.io/NCP/schemas/b01-review-response.v2.json"
)
CANDIDATE_SCHEMA_ID = (
    "https://sepahead.github.io/NCP/schemas/b01-review-source-candidate.v2.json"
)
REGISTRY_SCHEMA_ID = (
    "https://sepahead.github.io/NCP/schemas/proposed-decision-registry.v1.json"
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
    "OWNER_MODE_RESTRICTED_BUNDLE_STRUCTURAL_VALIDATION_ONLY_NO_AUTHORSHIP_"
    "HUMANNESS_"
    "SIGNATURE_CHALLENGE_ROLE_AUTHORITY_INDEPENDENCE_EXTERNAL_RECEIPT_TRUTH_"
    "ADMISSION_ADR_ACCEPTANCE_TASK_STATUS_PROTOCOL_CHANGE_OR_RELEASE_AUTHORITY"
)
CANDIDATE_CLAIM_BOUNDARY = (
    "UNAUTHENTICATED_OWNER_MODE_RESTRICTED_BUNDLE_STRUCTURAL_CANDIDATE_ONLY_"
    "EXTERNAL_VERIFIER_MUST_ESTABLISH_AUTHORSHIP_HUMANNESS_SIGNATURE_CHALLENGE_"
    "ROLE_AUTHORITY_INDEPENDENCE_RECEIPT_TRUTH_CURRENTNESS_REPLAY_EQUIVOCATION_"
    "REVOCATION_AND_ADMISSION_NO_ADR_TASK_PROTOCOL_OR_RELEASE_AUTHORITY"
)
SUBJECT_BINDING_SUITE = "ncp.b01-slot-subject-sha256.v1"
SUBJECT_BINDING_DOMAIN = b"ncp.b01-slot-subject-sha256.v1\x00"
RESPONSE_SEMANTIC_DOMAIN = b"ncp.b01-review-response-semantic.v1\x00"
DIGEST_ALGORITHM = "sha256(domain || u64be(projection_bytes) || projection)"
RAW_DIGEST_ALGORITHM = "sha256(raw bytes)"
SAFE_EVIDENCE_PATH_PATTERN = (
    r"^evidence/implementation/reviews/B01/"
    r"(?!\.\.(?:/|$))(?!.*(?:^|/)\.\.(?:/|$))[^\u0000-\u001f\u007f\\]+$"
)
MACHINE_MEMBERS = ("adr_id", "role_id", "subject")
HUMAN_SOURCE_MEMBERS = (
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
HUMAN_TRANSPORT_MEMBERS = ("subject_binding",)
SUBJECT_BINDING_SLOT_MEMBERS = (
    "slot_id",
    "adr_id",
    "distinct_identity_group",
    "identity_ordinal",
    "role_id",
    "role_label",
    "requires_independence",
    "required_evidence",
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
MAX_EVIDENCE_REFERENCES = 1_024
MAX_EVIDENCE_BUNDLE_BYTES = 16 * 1024 * 1024
MAX_REGISTRY_REPLAY_FILES = 2_048
MAX_REGISTRY_REPLAY_BYTES = 32 * 1024 * 1024
MAX_REGISTRY_EVIDENCE_BYTES = 1 * 1024 * 1024

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


def checked_repository_path(value: Any, label: str) -> str:
    text = exact_text(value, label, maximum=256)
    candidate = PurePosixPath(text)
    if (
        candidate.is_absolute()
        or text != candidate.as_posix()
        or "\\" in text
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in text)
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        fail(f"{label} must be one canonical repository-relative POSIX path")
    return text


def registry_evidence_paths(source: dict[str, Any]) -> tuple[str, ...]:
    records = source.get("review_records")
    if type(records) is not list or len(records) > MAX_REVIEW_RECORDS:
        fail("registry replay source has an invalid review-record roster")
    paths: set[str] = set()

    def add(reference: Any, label: str) -> None:
        if type(reference) is not dict:
            fail(f"{label} must be one evidence-reference object")
        relative = checked_repository_path(reference.get("path"), f"{label}.path")
        if not relative.startswith(EVIDENCE_PREFIX):
            fail(f"{label}.path must remain under the B01 review-evidence prefix")
        paths.add(relative)

    for record_index, record in enumerate(records):
        label = f"registry replay review_records[{record_index}]"
        if type(record) is not dict:
            fail(f"{label} must be one object")
        add(record.get("role_authorization"), f"{label}.role_authorization")
        add(record.get("external_receipt"), f"{label}.external_receipt")
        assessment = record.get("independence_assessment")
        if assessment is not None:
            add(assessment, f"{label}.independence_assessment")
        conditions = record.get("conditions")
        if type(conditions) is not list or len(conditions) > 16:
            fail(f"{label}.conditions has an invalid roster")
        for condition_index, condition in enumerate(conditions):
            condition_label = f"{label}.conditions[{condition_index}]"
            if type(condition) is not dict:
                fail(f"{condition_label} must be one object")
            evidence = condition.get("resolution_evidence")
            if type(evidence) is not list or len(evidence) > 16:
                fail(f"{condition_label}.resolution_evidence has an invalid roster")
            for evidence_index, reference in enumerate(evidence):
                add(
                    reference,
                    f"{condition_label}.resolution_evidence[{evidence_index}]",
                )
            closure = condition.get("closure")
            if closure is not None:
                if type(closure) is not dict:
                    fail(f"{condition_label}.closure must be one object")
                add(
                    closure.get("external_receipt"),
                    f"{condition_label}.closure.external_receipt",
                )
    if len(paths) > MAX_EVIDENCE_REFERENCES:
        fail("registry replay evidence roster exceeds its closed file limit")
    return tuple(sorted(paths))


def registry_replay_repository_paths(source: dict[str, Any]) -> tuple[str, ...]:
    decisions = source.get("decisions")
    if type(decisions) is not list or len(decisions) != EXPECTED_COUNTS["decisions"]:
        fail("registry replay source has an invalid decision roster")
    paths = set(FIXED_REGISTRY_REPLAY_PATHS)
    for decision_index, decision in enumerate(decisions):
        label = f"registry replay decisions[{decision_index}]"
        if type(decision) is not dict:
            fail(f"{label} must be one object")
        paths.add(checked_repository_path(decision.get("path"), f"{label}.path"))
        module_paths = decision.get("module_paths")
        if type(module_paths) is not list or len(module_paths) > 8:
            fail(f"{label}.module_paths has an invalid roster")
        for module_index, module_path in enumerate(module_paths):
            paths.add(
                checked_repository_path(
                    module_path,
                    f"{label}.module_paths[{module_index}]",
                )
            )
    if len(paths) > MAX_REGISTRY_REPLAY_FILES:
        fail("registry replay repository roster exceeds its closed file limit")
    return tuple(sorted(paths))


def snapshot_registry_replay_inputs(
    source: dict[str, Any],
    *,
    private_evidence_paths: set[str] | frozenset[str] = frozenset(),
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    repository_paths = registry_replay_repository_paths(source)
    evidence_paths = set(registry_evidence_paths(source))
    if not private_evidence_paths <= evidence_paths:
        fail("private evidence paths differ from the registry replay roster")
    repository, evidence = snapshot_registry_replay_paths(
        repository_paths,
        evidence_paths,
        private_evidence_paths=private_evidence_paths,
    )
    registry_replay_input_identities(repository, evidence)
    return repository, evidence


def snapshot_registry_replay_paths(
    repository_paths: tuple[str, ...],
    evidence_paths: set[str],
    *,
    private_evidence_paths: set[str] | frozenset[str],
    reader: Any | None = None,
    maximum_total_bytes: int = MAX_REGISTRY_REPLAY_BYTES,
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    """Read one closed replay roster without crossing its allocation budget."""

    if (
        type(repository_paths) is not tuple
        or type(evidence_paths) is not set
        or type(private_evidence_paths) not in {set, frozenset}
        or type(maximum_total_bytes) is not int
        or maximum_total_bytes <= 0
    ):
        fail("registry replay snapshot parameters are invalid")
    if not private_evidence_paths <= evidence_paths:
        fail("private evidence paths differ from the registry replay roster")
    repository_set = set(repository_paths)
    if len(repository_set) != len(repository_paths):
        fail("registry replay repository roster contains duplicate paths")
    if repository_set & evidence_paths:
        fail("registry replay repository and evidence paths overlap")
    if len(repository_set | evidence_paths) > MAX_REGISTRY_REPLAY_FILES:
        fail("registry replay roster exceeds its closed file limit")
    read = read_file if reader is None else reader
    if not callable(read):
        fail("registry replay reader must be callable")

    total = 0
    repository: dict[str, bytes] = {}
    evidence: dict[str, bytes] = {}

    def capture(relative: str, *, maximum_file_bytes: int) -> bytes:
        nonlocal total
        checked_repository_path(relative, "registry replay snapshot path")
        remaining = maximum_total_bytes - total
        if remaining <= 0:
            fail("registry replay inputs exceed their aggregate byte bound")
        maximum = min(maximum_file_bytes, remaining)
        raw = read(relative, maximum)
        if type(raw) is not bytes or not 1 <= len(raw) <= maximum:
            fail("registry replay reader returned invalid or over-budget bytes")
        total += len(raw)
        return raw

    for relative in repository_paths:
        repository[relative] = capture(
            relative,
            maximum_file_bytes=input_limits(relative),
        )
    for relative in sorted(evidence_paths - private_evidence_paths):
        evidence[relative] = capture(
            relative,
            maximum_file_bytes=MAX_REGISTRY_EVIDENCE_BYTES,
        )
    return repository, evidence


def registry_replay_input_identities(
    repository: dict[str, bytes], evidence: dict[str, bytes]
) -> list[dict[str, str | int]]:
    if type(repository) is not dict or type(evidence) is not dict:
        fail("registry replay inputs must be two exact byte maps")
    if set(repository) & set(evidence):
        fail("registry replay repository and evidence inputs overlap")
    combined = {**repository, **evidence}
    if not 1 <= len(combined) <= MAX_REGISTRY_REPLAY_FILES:
        fail("registry replay input count is outside its closed bound")
    total = 0
    identities: list[dict[str, str | int]] = []
    for relative in sorted(combined):
        checked_repository_path(relative, "registry replay input path")
        raw = combined[relative]
        maximum = (
            MAX_REGISTRY_EVIDENCE_BYTES
            if relative in evidence
            else input_limits(relative)
        )
        if type(raw) is not bytes or not 1 <= len(raw) <= maximum:
            fail("registry replay input bytes are outside their per-file bound")
        total += len(raw)
        if total > MAX_REGISTRY_REPLAY_BYTES:
            fail("registry replay inputs exceed their aggregate byte bound")
        identities.append(identity(relative, raw))
    return identities


def validate_registry_replay_identities(value: Any) -> None:
    if type(value) is not list or not 1 <= len(value) <= MAX_REGISTRY_REPLAY_FILES:
        fail("registry replay identity roster is outside its closed file bound")
    paths: list[str] = []
    total = 0
    for index, item in enumerate(value):
        label = f"registry replay identities[{index}]"
        item = exact_keys(item, {"path", "sha256", "bytes"}, label)
        paths.append(checked_repository_path(item["path"], f"{label}.path"))
        digest = item["sha256"]
        if type(digest) is not str or HEX64.fullmatch(digest) is None:
            fail(f"{label}.sha256 must be one lowercase SHA-256 value")
        byte_count = item["bytes"]
        maximum = (
            MAX_REGISTRY_EVIDENCE_BYTES
            if paths[-1].startswith(EVIDENCE_PREFIX)
            else input_limits(paths[-1])
        )
        if type(byte_count) is not int or not 1 <= byte_count <= maximum:
            fail(f"{label}.bytes is outside its per-file bound")
        total += byte_count
        if total > MAX_REGISTRY_REPLAY_BYTES:
            fail("registry replay identities exceed their aggregate byte bound")
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        fail("registry replay identity paths are duplicated or out of order")


def require_absent_promotion_target(path: Path) -> None:
    """Require one path to remain absent for a non-normative registry replay."""

    try:
        os.lstat(path)
    except FileNotFoundError:
        return
    except OSError as error:
        fail(f"cannot inspect the registry promotion target (errno={error.errno})")
    fail("registry promotion target exists during non-normative replay")


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
        ).encode()
    except (RecursionError, TypeError, UnicodeError, ValueError) as error:
        raise ReviewerKitError(f"cannot encode reviewer kit: {error}") from error
    if len(raw) > MAX_KIT_BYTES:
        fail(f"generated reviewer kit exceeds {MAX_KIT_BYTES} bytes")
    return raw


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (RecursionError, TypeError, UnicodeError, ValueError) as error:
        raise ReviewerKitError(f"cannot encode canonical JSON: {error}") from error


def domain_commitment(domain: bytes, value: Any) -> dict[str, Any]:
    projection = canonical_json_bytes(value)
    digest = hashlib.sha256(
        domain + len(projection).to_bytes(8, "big") + projection
    ).hexdigest()
    return {
        "digest_algorithm": DIGEST_ALGORITHM,
        "domain_hex": domain.hex(),
        "projection_bytes": len(projection),
        "sha256": digest,
    }


def subject_binding_value(
    slot: dict[str, Any], subject: dict[str, Any]
) -> dict[str, str]:
    if type(slot) is not dict or any(
        name not in slot for name in SUBJECT_BINDING_SLOT_MEMBERS
    ):
        fail("subject binding requires one complete generated review slot")
    projection = {
        "slot": {
            name: copy.deepcopy(slot[name]) for name in SUBJECT_BINDING_SLOT_MEMBERS
        },
        "subject": copy.deepcopy(subject),
    }
    return {
        "suite": SUBJECT_BINDING_SUITE,
        "sha256": domain_commitment(SUBJECT_BINDING_DOMAIN, projection)["sha256"],
    }


def raw_response_identity(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_RESPONSE_BYTES:
        fail("raw review response bytes are outside the supported bounds")
    return {
        "logical_name": "response.json",
        "digest_algorithm": RAW_DIGEST_ALGORITHM,
        "sha256": sha256(raw),
        "bytes": len(raw),
        "media_type": "application/json",
    }


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
            "subjectBinding",
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
        if name == "subjectBinding":
            continue
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
    expected_response_properties = {
        "schema",
        "slot_id",
        *HUMAN_TRANSPORT_MEMBERS,
        *HUMAN_SOURCE_MEMBERS,
    }
    if set(response_properties) != expected_response_properties:
        fail("response schema root fields differ from the human response contract")
    review_properties = registry_defs.get("reviewRecord", {}).get("properties")
    if type(review_properties) is not dict:
        fail("registry review-record properties are missing")
    for name in HUMAN_SOURCE_MEMBERS:
        if response_properties[name] != review_properties.get(name):
            fail(f"response schema property {name} differs from registry policy")
    if response_properties["subject_binding"] != {"$ref": "#/$defs/subjectBinding"}:
        fail("response schema subject binding differs from the transport contract")
    if response_schema.get("required") != [
        "schema",
        "slot_id",
        *HUMAN_TRANSPORT_MEMBERS,
        *HUMAN_SOURCE_MEMBERS,
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
            "subjectBinding",
            "rawResponseIdentity",
            "digestCommitment",
            "responseIdentity",
            "evidenceBundle",
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
    if not (
        response_defs["subjectBinding"]
        == kit_defs.get("subjectBinding")
        == candidate_defs["subjectBinding"]
    ):
        fail("subject-binding schema differs across the v2 review chain")
    if candidate_defs["rawResponseIdentity"] != {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "logical_name",
            "digest_algorithm",
            "sha256",
            "bytes",
            "media_type",
        ],
        "properties": {
            "logical_name": {"const": "response.json"},
            "digest_algorithm": {"const": RAW_DIGEST_ALGORITHM},
            "sha256": {"$ref": "#/$defs/sha256"},
            "bytes": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_RESPONSE_BYTES,
            },
            "media_type": {"const": "application/json"},
        },
    }:
        fail("candidate raw-response identity schema changed")
    if candidate_defs["digestCommitment"] != {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "digest_algorithm",
            "domain_hex",
            "projection_bytes",
            "sha256",
        ],
        "properties": {
            "digest_algorithm": {"const": DIGEST_ALGORITHM},
            "domain_hex": {"const": RESPONSE_SEMANTIC_DOMAIN.hex()},
            "projection_bytes": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_RESPONSE_BYTES,
            },
            "sha256": {"$ref": "#/$defs/sha256"},
        },
    }:
        fail("candidate response semantic-commitment schema changed")
    if candidate_defs["responseIdentity"] != {
        "type": "object",
        "additionalProperties": False,
        "required": ["raw", "semantic"],
        "properties": {
            "raw": {"$ref": "#/$defs/rawResponseIdentity"},
            "semantic": {"$ref": "#/$defs/digestCommitment"},
        },
    }:
        fail("candidate response-identity schema changed")
    if candidate_defs["evidenceBundle"] != {
        "type": "object",
        "additionalProperties": False,
        "required": ["files", "total_files", "total_bytes"],
        "properties": {
            "files": {
                "type": "array",
                "minItems": 2,
                "maxItems": MAX_EVIDENCE_REFERENCES,
                "uniqueItems": True,
                "items": {"$ref": "#/$defs/fileIdentity"},
            },
            "total_files": {
                "type": "integer",
                "minimum": 2,
                "maximum": MAX_EVIDENCE_REFERENCES,
            },
            "total_bytes": {
                "type": "integer",
                "minimum": 2,
                "maximum": MAX_EVIDENCE_BUNDLE_BYTES,
            },
        },
    }:
        fail("candidate evidence-bundle schema changed")

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
        "admission_status",
        "claim_boundary",
        "slot_id",
        "subject_binding",
        "response_identity",
        "evidence_bundle",
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
        "admission_status",
        "claim_boundary",
        "slot_id",
        "subject_binding",
        "response_identity",
        "evidence_bundle",
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
        "admission_status": {"const": "NOT_EVALUATED"},
        "claim_boundary": {"const": CANDIDATE_CLAIM_BOUNDARY},
        "slot_id": copy.deepcopy(response_properties["slot_id"]),
        "subject_binding": {"$ref": "#/$defs/subjectBinding"},
        "response_identity": {"$ref": "#/$defs/responseIdentity"},
        "evidence_bundle": {"$ref": "#/$defs/evidenceBundle"},
        "validation_context": {"$ref": "#/$defs/validationContext"},
        "registry_mutation": {"const": False},
        "external_verifier_required": {"const": True},
        "source_record": {"$ref": "#/$defs/sourceRecord"},
    }
    if candidate_properties != expected_candidate_properties:
        fail("candidate schema root policy changed")
    expected_context_properties = {}
    for name, path in (
        ("private_bundle_preflight", PREFLIGHT_RELATIVE),
        ("bounded_json_reader", BOUNDED_JSON_RELATIVE),
        ("immutable_git_reader", IMMUTABLE_GIT_RELATIVE),
        ("schema_validator", SCHEMA_VALIDATOR_RELATIVE),
        ("review_request", REQUEST_RELATIVE),
        ("review_packet", REVIEW_PACKET_RELATIVE),
        ("reviewer_kit_generator", SCRIPT_RELATIVE),
        ("reviewer_kit", OUTPUT_RELATIVE),
        ("reviewer_kit_schema", KIT_SCHEMA_RELATIVE),
        ("response_schema", RESPONSE_SCHEMA_RELATIVE),
        ("candidate_schema", CANDIDATE_SCHEMA_RELATIVE),
        ("registry_generator", REGISTRY_GENERATOR_RELATIVE),
        ("registry_schema", REGISTRY_SCHEMA_RELATIVE),
        ("validated_against_registry_source", REGISTRY_SOURCE_RELATIVE),
        (
            "validated_against_proposed_registry",
            CURRENT_PROPOSED_REGISTRY_RELATIVE,
        ),
    ):
        expected_context_properties[name] = {
            "allOf": [
                {"$ref": "#/$defs/fileIdentity"},
                {"properties": {"path": {"const": path}}},
            ]
        }
        if name == "registry_schema":
            expected_context_properties["registry_replay_inputs"] = {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_REGISTRY_REPLAY_FILES,
                "uniqueItems": True,
                "items": {"$ref": "#/$defs/fileIdentity"},
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
        generated_slot = {
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
        generated_slot["subject_binding"] = subject_binding_value(
            generated_slot, slot["subject"]
        )
        generated_slots.append(generated_slot)

    kit = {
        "schema": KIT_SCHEMA,
        "normative": False,
        "authorizing": False,
        "minimum_only": True,
        "claim_boundary": KIT_CLAIM_BOUNDARY,
        "generated_by": identity(SCRIPT_RELATIVE, snapshots[SCRIPT_RELATIVE]),
        "inputs": {
            "private_bundle_preflight": identity(
                PREFLIGHT_RELATIVE, snapshots[PREFLIGHT_RELATIVE]
            ),
            "bounded_json_reader": identity(
                BOUNDED_JSON_RELATIVE, snapshots[BOUNDED_JSON_RELATIVE]
            ),
            "immutable_git_reader": identity(
                IMMUTABLE_GIT_RELATIVE, snapshots[IMMUTABLE_GIT_RELATIVE]
            ),
            "schema_validator": identity(
                SCHEMA_VALIDATOR_RELATIVE, snapshots[SCHEMA_VALIDATOR_RELATIVE]
            ),
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
            "human_response_members": list(HUMAN_SOURCE_MEMBERS),
            "human_transport_members": list(HUMAN_TRANSPORT_MEMBERS),
            "derived_member_forbidden": True,
            "raw_response_identity_required": True,
            "registry_mutation": False,
            "output": ("OWNER_MODE_RESTRICTED_BUNDLE_STDOUT_ONLY_STRUCTURAL_CANDIDATE"),
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
    if relative in {SCRIPT_RELATIVE, PREFLIGHT_RELATIVE}:
        return MAX_SCRIPT_BYTES
    return MAX_INPUT_BYTES


def snapshot_inputs() -> dict[str, bytes]:
    paths = (
        SCRIPT_RELATIVE,
        PREFLIGHT_RELATIVE,
        BOUNDED_JSON_RELATIVE,
        SCHEMA_VALIDATOR_RELATIVE,
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
        ImportError,
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
        "human_response_members": list(HUMAN_SOURCE_MEMBERS),
        "human_transport_members": list(HUMAN_TRANSPORT_MEMBERS),
        "derived_member_forbidden": True,
        "raw_response_identity_required": True,
        "registry_mutation": False,
        "output": "OWNER_MODE_RESTRICTED_BUNDLE_STDOUT_ONLY_STRUCTURAL_CANDIDATE",
        "output_schema": CANDIDATE_SCHEMA,
        "claim_boundary": MATERIALIZATION_CLAIM_BOUNDARY,
    }:
        fail("reviewer kit materialization boundary changed")
    subjects = {
        decision["adr_id"]: decision["subject"] for decision in kit["decisions"]
    }
    for slot in kit["slots"]:
        subject = subjects.get(slot["adr_id"])
        if type(subject) is not dict or slot[
            "subject_binding"
        ] != subject_binding_value(slot, subject):
            fail("reviewer kit slot subject binding differs from its exact subject")
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


def response_evidence_references(response: dict[str, Any]) -> list[dict[str, Any]]:
    references = [response["role_authorization"], response["external_receipt"]]
    independence = response["independence_assessment"]
    if independence is not None:
        references.append(independence)
    for condition in response["conditions"]:
        references.extend(condition["resolution_evidence"])
        closure = condition["closure"]
        if closure is not None:
            references.append(closure["external_receipt"])
    if not 2 <= len(references) <= MAX_EVIDENCE_REFERENCES:
        fail(
            "review response evidence-reference count is outside "
            f"2..{MAX_EVIDENCE_REFERENCES}"
        )
    return references


def evidence_bundle_projection(response: dict[str, Any]) -> dict[str, Any]:
    references = response_evidence_references(response)
    by_path: dict[str, dict[str, Any]] = {}
    for reference in references:
        path = reference["path"]
        prior = by_path.get(path)
        observed = {
            "path": path,
            "sha256": reference["sha256"],
            "bytes": reference["bytes"],
        }
        if prior is not None and prior != observed:
            fail("one evidence path has conflicting identities in the response")
        by_path[path] = observed
    files = [by_path[path] for path in sorted(by_path)]
    total_bytes = sum(item["bytes"] for item in files)
    if not 2 <= len(files) <= MAX_EVIDENCE_REFERENCES:
        fail("review response must reference at least two distinct evidence files")
    if not 2 <= total_bytes <= MAX_EVIDENCE_BUNDLE_BYTES:
        fail("review response evidence byte count exceeds its aggregate bound")
    return {
        "files": files,
        "total_files": len(files),
        "total_bytes": total_bytes,
    }


def evidence_bundle_value(
    response: dict[str, Any], artifact_overrides: dict[str, bytes]
) -> dict[str, Any]:
    if type(artifact_overrides) is not dict:
        fail("private bundle evidence overrides must be one exact map")
    projected = evidence_bundle_projection(response)
    by_path = {item["path"]: item for item in projected["files"]}
    if set(artifact_overrides) != set(by_path):
        fail("private bundle evidence files differ from the exact response roster")
    total_bytes = 0
    for path, expected in by_path.items():
        raw = artifact_overrides[path]
        if type(raw) is not bytes:
            fail("private bundle evidence override is not exact bytes")
        if len(raw) != expected["bytes"] or sha256(raw) != expected["sha256"]:
            fail("private bundle evidence bytes differ from the response identity")
        total_bytes += len(raw)
        if total_bytes > MAX_EVIDENCE_BUNDLE_BYTES:
            fail("private bundle evidence exceeds the 16 MiB aggregate limit")
    if total_bytes != projected["total_bytes"]:
        fail("private bundle evidence aggregate byte count changed")
    return projected


def execute_exact_registry_generator(
    source_bytes: bytes,
    candidate: dict[str, Any],
    *,
    artifact_overrides: dict[str, bytes],
    immutable_git_source: bytes,
    bounded_json_source: bytes,
    schema_validator_source: bytes,
    repository_snapshots: dict[str, bytes],
) -> tuple[dict[str, Any], bytes]:
    exact_sources = {
        IMMUTABLE_GIT_RELATIVE: immutable_git_source,
        BOUNDED_JSON_RELATIVE: bounded_json_source,
        SCHEMA_VALIDATOR_RELATIVE: schema_validator_source,
    }
    for relative, raw in exact_sources.items():
        if type(raw) is not bytes or not 1 <= len(raw) <= input_limits(relative):
            fail(f"exact replay helper {relative} is invalid")
    expected_repository_paths = set(registry_replay_repository_paths(candidate))
    expected_evidence_paths = set(registry_evidence_paths(candidate))
    if type(repository_snapshots) is not dict or set(repository_snapshots) != (
        expected_repository_paths
    ):
        fail("exact registry replay repository roster differs from its source")
    if type(artifact_overrides) is not dict or set(artifact_overrides) != (
        expected_evidence_paths
    ):
        fail("exact registry replay evidence roster differs from its source")
    registry_replay_input_identities(repository_snapshots, artifact_overrides)
    if repository_snapshots[REGISTRY_GENERATOR_RELATIVE] != source_bytes:
        fail("exact registry generator differs from its replay snapshot")

    promotion_target = ROOT / PROMOTION_TARGET_RELATIVE
    require_absent_promotion_target(promotion_target)
    helper_name = "_ncp_b01_registry_immutable_git"
    prior_helper = sys.modules.get(helper_name)
    helper = types.ModuleType(helper_name)
    helper.__file__ = str(ROOT / IMMUTABLE_GIT_RELATIVE)
    exact_module_names = ("bounded_json", "validate_evidence_schemas")
    prior_modules = {name: sys.modules.get(name) for name in exact_module_names}
    try:
        bounded_module = types.ModuleType("bounded_json")
        bounded_module.__file__ = str(ROOT / BOUNDED_JSON_RELATIVE)
        sys.modules["bounded_json"] = bounded_module
        bounded_code = compile(
            bounded_json_source.decode("utf-8", errors="strict"),
            BOUNDED_JSON_RELATIVE,
            "exec",
            dont_inherit=True,
            optimize=0,
        )
        exec(bounded_code, bounded_module.__dict__)  # noqa: S102 - exact bound bytes

        validator_module = types.ModuleType("validate_evidence_schemas")
        validator_module.__file__ = str(ROOT / SCHEMA_VALIDATOR_RELATIVE)
        sys.modules["validate_evidence_schemas"] = validator_module
        validator_code = compile(
            schema_validator_source.decode("utf-8", errors="strict"),
            SCHEMA_VALIDATOR_RELATIVE,
            "exec",
            dont_inherit=True,
            optimize=0,
        )
        exec(  # noqa: S102 - exact bound bytes
            validator_code,
            validator_module.__dict__,
        )

        sys.modules[helper_name] = helper
        helper_code = compile(
            immutable_git_source.decode("utf-8", errors="strict"),
            IMMUTABLE_GIT_RELATIVE,
            "exec",
            dont_inherit=True,
            optimize=0,
        )
        exec(helper_code, helper.__dict__)  # noqa: S102 - exact kit-bound bytes
        immutable_commit_tree = helper.__dict__.get("commit_tree")
        immutable_blob_snapshot = helper.__dict__.get("blob_snapshot")
        if not callable(immutable_commit_tree) or not callable(immutable_blob_snapshot):
            fail("exact immutable Git helper lacks its subject-reader API")
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
        relative_path = module.__dict__.get("relative_path")
        build_registry = module.__dict__.get("build_registry")
        serialize_registry = module.__dict__.get("generated_bytes")
        load_registry_json = module.__dict__.get("load_json_bytes")
        if not all(
            callable(function)
            for function in (
                relative_path,
                build_registry,
                serialize_registry,
                load_registry_json,
            )
        ):
            fail("exact registry generator lacks its build or serialization API")
        subject_cache: dict[tuple[str, str], tuple[str, bytes]] = {}
        repository_reads: set[str] = set()
        bounded_reads: set[str] = set()

        def closed_repository_reader(
            repository_path: str,
            *,
            maximum_bytes: int,
            label: str,
        ) -> bytes:
            relative = checked_repository_path(repository_path, label)
            raw = repository_snapshots.get(relative)
            if raw is None:
                fail("exact registry generator requested an unbound repository input")
            if type(maximum_bytes) is not int or not 1 <= len(raw) <= maximum_bytes:
                fail("exact registry input exceeds the generator's requested bound")
            repository_reads.add(relative)
            return raw

        def closed_bounded_reader(
            path: Path,
            *,
            limits: Any,
            label: str,
        ) -> bytes:
            try:
                relative = Path(path).relative_to(ROOT).as_posix()
            except (TypeError, ValueError):
                fail("exact registry generator requested an external bounded input")
            if relative != CLOSURE_SOURCE_RELATIVE:
                fail("exact registry generator requested an unbound bounded input")
            raw = repository_snapshots.get(relative)
            minimum = getattr(limits, "minimum_bytes", None)
            maximum = getattr(limits, "maximum_bytes", None)
            if (
                type(raw) is not bytes
                or type(limits) is not bounded_module.FileSnapshotLimits
                or type(minimum) is not int
                or type(maximum) is not int
                or not minimum <= len(raw) <= maximum
            ):
                fail("exact bounded registry input exceeds its requested limits")
            if label != CLOSURE_SOURCE_RELATIVE:
                fail("exact bounded registry input changed its diagnostic label")
            bounded_reads.add(relative)
            return raw

        def immutable_resolve_git_subject(
            source_commit: str, repository_path: str
        ) -> tuple[str, bytes]:
            relative = relative_path(
                repository_path,
                "review subject repository path",
            )
            key = (source_commit, relative)
            cached = subject_cache.get(key)
            if cached is not None:
                return cached
            tree = immutable_commit_tree(source_commit, root=ROOT)
            snapshot = immutable_blob_snapshot(
                source_commit,
                relative,
                maximum=MAX_INPUT_BYTES,
                root=ROOT,
            )
            result = (tree, snapshot.raw)
            subject_cache[key] = result
            return result

        module.__dict__["GIT"] = None
        module.__dict__["resolve_git_subject"] = immutable_resolve_git_subject
        module.__dict__["read_repository_regular_file"] = closed_repository_reader
        module.__dict__["read_bounded_regular_file"] = closed_bounded_reader

        class CapturedAbsentPromotionTarget:
            @staticmethod
            def exists() -> bool:
                return False

        module.__dict__["PROMOTION_TARGET"] = CapturedAbsentPromotionTarget()
        generated = build_registry(
            candidate,
            artifact_overrides=artifact_overrides,
            closure_source_override=None,
            closure_schema_override=repository_snapshots[CLOSURE_SCHEMA_RELATIVE],
            closure_artifact_overrides={
                SEMANTIC_CORPUS_RELATIVE: repository_snapshots[SEMANTIC_CORPUS_RELATIVE]
            },
            subject_resolver=immutable_resolve_git_subject,
            policy_overrides={
                REGISTRY_GENERATOR_RELATIVE: source_bytes,
                REGISTRY_SCHEMA_RELATIVE: repository_snapshots[
                    REGISTRY_SCHEMA_RELATIVE
                ],
            },
            packet_override=repository_snapshots[REVIEW_PACKET_RELATIVE],
        )
        expected_reader_paths = expected_repository_paths - set(
            FIXED_REGISTRY_REPLAY_PATHS
        )
        if repository_reads != expected_reader_paths:
            fail("exact registry generator did not consume its closed ADR input roster")
        if bounded_reads != {CLOSURE_SOURCE_RELATIVE}:
            fail("exact registry generator did not consume its closed bounded roster")
        if not subject_cache:
            fail("exact registry generator did not resolve a bound Git subject")
        require_pinned_validator = validator_module.__dict__.get(
            "require_pinned_validator"
        )
        validate_instance = validator_module.__dict__.get("validate_instance")
        registry_schema_id = validator_module.__dict__.get(
            "DECISION_REGISTRY_SCHEMA_ID"
        )
        if (
            not callable(require_pinned_validator)
            or not callable(validate_instance)
            or registry_schema_id != REGISTRY_SCHEMA_ID
        ):
            fail("exact schema validator lacks its pinned registry API")
        parsed_registry_schema = load_registry_json(
            repository_snapshots[REGISTRY_SCHEMA_RELATIVE],
            REGISTRY_SCHEMA_RELATIVE,
        )
        require_pinned_validator()
        validate_instance(
            parsed_registry_schema,
            generated,
            "exact replay proposed decision registry",
            expected_schema_id=registry_schema_id,
        )
        serialized = serialize_registry(generated)
        require_absent_promotion_target(promotion_target)
    except (
        AttributeError,
        ImportError,
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
    finally:
        if prior_helper is None:
            sys.modules.pop(helper_name, None)
        else:
            sys.modules[helper_name] = prior_helper
        for name in reversed(exact_module_names):
            prior = prior_modules[name]
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior
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
    snapshots = snapshot_inputs()
    if build_kit_from_snapshots(snapshots) != kit:
        fail("review-capture fixed inputs differ from the reviewer kit")
    for relative in (
        REGISTRY_SOURCE_RELATIVE,
        CURRENT_PROPOSED_REGISTRY_RELATIVE,
    ):
        if relative in snapshots:
            fail("review-capture snapshot contains a duplicate input path")
        snapshots[relative] = read_file(relative, MAX_INPUT_BYTES)
    source = parse_object(
        snapshots[REGISTRY_SOURCE_RELATIVE],
        REGISTRY_SOURCE_RELATIVE,
        MAX_INPUT_BYTES,
    )
    repository_snapshots, evidence_snapshots = snapshot_registry_replay_inputs(source)
    if kit["subject_cut"]["review_packet"] != identity(
        REVIEW_PACKET_RELATIVE,
        repository_snapshots[REVIEW_PACKET_RELATIVE],
    ):
        fail("review-capture packet differs from the reviewer kit subject")
    for relative, raw in {**repository_snapshots, **evidence_snapshots}.items():
        if relative in snapshots and snapshots[relative] != raw:
            fail("review-capture replay input differs across one snapshot")
        snapshots[relative] = raw
    generated, serialized = execute_exact_registry_generator(
        snapshots[REGISTRY_GENERATOR_RELATIVE],
        source,
        artifact_overrides=evidence_snapshots,
        immutable_git_source=snapshots[IMMUTABLE_GIT_RELATIVE],
        bounded_json_source=snapshots[BOUNDED_JSON_RELATIVE],
        schema_validator_source=snapshots[SCHEMA_VALIDATOR_RELATIVE],
        repository_snapshots=repository_snapshots,
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
    raw_response: bytes,
    artifact_overrides: dict[str, bytes],
    registry_source_override: bytes | None = None,
    proposed_registry_override: bytes | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    if (
        parse_object(raw_response, "private response.json", MAX_RESPONSE_BYTES)
        != response
    ):
        fail("parsed response differs from the exact private response bytes")
    source_bytes = (
        read_file(REGISTRY_SOURCE_RELATIVE, MAX_INPUT_BYTES)
        if registry_source_override is None
        else registry_source_override
    )
    if type(source_bytes) is not bytes or not 1 <= len(source_bytes) <= MAX_INPUT_BYTES:
        fail("review materialization source override is invalid")
    proposed_bytes = (
        read_file(CURRENT_PROPOSED_REGISTRY_RELATIVE, MAX_INPUT_BYTES)
        if proposed_registry_override is None
        else proposed_registry_override
    )
    if (
        type(proposed_bytes) is not bytes
        or not 1 <= len(proposed_bytes) <= MAX_INPUT_BYTES
    ):
        fail("review materialization proposed-registry override is invalid")
    materialization_snapshots = {
        PREFLIGHT_RELATIVE: read_file(PREFLIGHT_RELATIVE, MAX_SCRIPT_BYTES),
        BOUNDED_JSON_RELATIVE: read_file(BOUNDED_JSON_RELATIVE, MAX_INPUT_BYTES),
        IMMUTABLE_GIT_RELATIVE: read_file(IMMUTABLE_GIT_RELATIVE, MAX_INPUT_BYTES),
        SCHEMA_VALIDATOR_RELATIVE: read_file(
            SCHEMA_VALIDATOR_RELATIVE, MAX_INPUT_BYTES
        ),
        SCRIPT_RELATIVE: read_file(SCRIPT_RELATIVE, MAX_SCRIPT_BYTES),
        REQUEST_RELATIVE: read_file(REQUEST_RELATIVE, MAX_REQUEST_BYTES),
        REVIEW_PACKET_RELATIVE: read_file(REVIEW_PACKET_RELATIVE, MAX_INPUT_BYTES),
        OUTPUT_RELATIVE: read_file(OUTPUT_RELATIVE, MAX_KIT_BYTES),
        KIT_SCHEMA_RELATIVE: read_file(KIT_SCHEMA_RELATIVE, MAX_SCHEMA_BYTES),
        RESPONSE_SCHEMA_RELATIVE: read_file(RESPONSE_SCHEMA_RELATIVE, MAX_SCHEMA_BYTES),
        CANDIDATE_SCHEMA_RELATIVE: read_file(
            CANDIDATE_SCHEMA_RELATIVE, MAX_SCHEMA_BYTES
        ),
        REGISTRY_GENERATOR_RELATIVE: read_file(
            REGISTRY_GENERATOR_RELATIVE, MAX_INPUT_BYTES
        ),
        REGISTRY_SCHEMA_RELATIVE: read_file(REGISTRY_SCHEMA_RELATIVE, MAX_INPUT_BYTES),
        REGISTRY_SOURCE_RELATIVE: source_bytes,
        CURRENT_PROPOSED_REGISTRY_RELATIVE: proposed_bytes,
    }
    for key, relative in (
        ("private_bundle_preflight", PREFLIGHT_RELATIVE),
        ("bounded_json_reader", BOUNDED_JSON_RELATIVE),
        ("immutable_git_reader", IMMUTABLE_GIT_RELATIVE),
        ("schema_validator", SCHEMA_VALIDATOR_RELATIVE),
        ("review_request", REQUEST_RELATIVE),
        ("reviewer_kit_schema", KIT_SCHEMA_RELATIVE),
        ("review_response_schema", RESPONSE_SCHEMA_RELATIVE),
        ("review_source_candidate_schema", CANDIDATE_SCHEMA_RELATIVE),
        ("decision_registry_generator", REGISTRY_GENERATOR_RELATIVE),
        ("decision_registry_schema", REGISTRY_SCHEMA_RELATIVE),
    ):
        if kit["inputs"][key] != identity(
            relative, materialization_snapshots[relative]
        ):
            fail(f"materialization input {relative} differs from the reviewer kit")
    if kit["generated_by"] != identity(
        SCRIPT_RELATIVE, materialization_snapshots[SCRIPT_RELATIVE]
    ):
        fail("materialization reviewer-kit generator identity changed")
    if kit["subject_cut"]["review_packet"] != identity(
        REVIEW_PACKET_RELATIVE, materialization_snapshots[REVIEW_PACKET_RELATIVE]
    ):
        fail("materialization review packet identity changed")
    if identity(
        OUTPUT_RELATIVE, materialization_snapshots[OUTPUT_RELATIVE]
    ) != identity(OUTPUT_RELATIVE, generated_bytes(kit)):
        fail("materialization reviewer kit is missing or stale")
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
    expected_binding = subject_binding_value(slot, subjects[slot["adr_id"]])
    if response["subject_binding"] != expected_binding:
        fail("review response subject binding differs from the selected current slot")
    evidence_bundle = evidence_bundle_value(response, artifact_overrides)
    record = {name: copy.deepcopy(response[name]) for name in HUMAN_SOURCE_MEMBERS}
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
    repository_snapshots, current_evidence_snapshots = snapshot_registry_replay_inputs(
        source
    )
    if set(current_evidence_snapshots) & set(artifact_overrides):
        fail("private response evidence reuses an existing registry evidence path")
    for relative, raw in {
        **repository_snapshots,
        **current_evidence_snapshots,
    }.items():
        if relative in materialization_snapshots and (
            materialization_snapshots[relative] != raw
        ):
            fail("materialization replay input differs across one snapshot")
        materialization_snapshots[relative] = raw
    combined_evidence_snapshots = {
        **current_evidence_snapshots,
        **artifact_overrides,
    }
    records = source.get("review_records")
    if type(records) is not list or len(records) >= MAX_REVIEW_RECORDS:
        fail("decision-registry source cannot accept another bounded review record")
    current_generated, current_serialized = execute_exact_registry_generator(
        materialization_snapshots[REGISTRY_GENERATOR_RELATIVE],
        source,
        artifact_overrides=current_evidence_snapshots,
        immutable_git_source=materialization_snapshots[IMMUTABLE_GIT_RELATIVE],
        bounded_json_source=materialization_snapshots[BOUNDED_JSON_RELATIVE],
        schema_validator_source=materialization_snapshots[SCHEMA_VALIDATOR_RELATIVE],
        repository_snapshots=repository_snapshots,
    )
    if (
        current_serialized
        != materialization_snapshots[CURRENT_PROPOSED_REGISTRY_RELATIVE]
    ):
        fail(
            "materialization registry source and proposed registry differ "
            "inside one exact snapshot"
        )
    review_capture_phase_value(source, current_generated)
    candidate = copy.deepcopy(source)
    candidate["review_records"].append(record)
    generated, _serialized = execute_exact_registry_generator(
        materialization_snapshots[REGISTRY_GENERATOR_RELATIVE],
        candidate,
        artifact_overrides=combined_evidence_snapshots,
        immutable_git_source=materialization_snapshots[IMMUTABLE_GIT_RELATIVE],
        bounded_json_source=materialization_snapshots[BOUNDED_JSON_RELATIVE],
        schema_validator_source=materialization_snapshots[SCHEMA_VALIDATOR_RELATIVE],
        repository_snapshots=repository_snapshots,
    )
    matches = [
        item
        for item in generated.get("review_records", [])
        if item.get("review_id") == record["review_id"]
    ]
    if len(matches) != 1:
        fail("frozen registry validation did not retain one candidate review")
    overridden_paths = set()
    if registry_source_override is not None:
        overridden_paths.add(REGISTRY_SOURCE_RELATIVE)
    if proposed_registry_override is not None:
        overridden_paths.add(CURRENT_PROPOSED_REGISTRY_RELATIVE)
    rejoin_snapshots = {
        relative: raw
        for relative, raw in materialization_snapshots.items()
        if relative not in overridden_paths
    }
    if any(
        read_file(relative, input_limits(relative)) != raw
        for relative, raw in rejoin_snapshots.items()
    ):
        fail("review materialization inputs changed during validation")
    validation_context = {
        "private_bundle_preflight": identity(
            PREFLIGHT_RELATIVE, materialization_snapshots[PREFLIGHT_RELATIVE]
        ),
        "bounded_json_reader": identity(
            BOUNDED_JSON_RELATIVE, materialization_snapshots[BOUNDED_JSON_RELATIVE]
        ),
        "immutable_git_reader": identity(
            IMMUTABLE_GIT_RELATIVE,
            materialization_snapshots[IMMUTABLE_GIT_RELATIVE],
        ),
        "schema_validator": identity(
            SCHEMA_VALIDATOR_RELATIVE,
            materialization_snapshots[SCHEMA_VALIDATOR_RELATIVE],
        ),
        "review_request": identity(
            REQUEST_RELATIVE, materialization_snapshots[REQUEST_RELATIVE]
        ),
        "review_packet": identity(
            REVIEW_PACKET_RELATIVE, materialization_snapshots[REVIEW_PACKET_RELATIVE]
        ),
        "reviewer_kit_generator": identity(
            SCRIPT_RELATIVE, materialization_snapshots[SCRIPT_RELATIVE]
        ),
        "reviewer_kit": identity(OUTPUT_RELATIVE, generated_bytes(kit)),
        "reviewer_kit_schema": identity(
            KIT_SCHEMA_RELATIVE, materialization_snapshots[KIT_SCHEMA_RELATIVE]
        ),
        "response_schema": identity(
            RESPONSE_SCHEMA_RELATIVE,
            materialization_snapshots[RESPONSE_SCHEMA_RELATIVE],
        ),
        "candidate_schema": identity(
            CANDIDATE_SCHEMA_RELATIVE,
            materialization_snapshots[CANDIDATE_SCHEMA_RELATIVE],
        ),
        "registry_generator": identity(
            REGISTRY_GENERATOR_RELATIVE,
            materialization_snapshots[REGISTRY_GENERATOR_RELATIVE],
        ),
        "registry_schema": identity(
            REGISTRY_SCHEMA_RELATIVE,
            materialization_snapshots[REGISTRY_SCHEMA_RELATIVE],
        ),
        "registry_replay_inputs": registry_replay_input_identities(
            repository_snapshots,
            combined_evidence_snapshots,
        ),
        "validated_against_registry_source": identity(
            REGISTRY_SOURCE_RELATIVE,
            materialization_snapshots[REGISTRY_SOURCE_RELATIVE],
        ),
        "validated_against_proposed_registry": identity(
            CURRENT_PROPOSED_REGISTRY_RELATIVE,
            materialization_snapshots[CURRENT_PROPOSED_REGISTRY_RELATIVE],
        ),
    }
    response_identity = {
        "raw": raw_response_identity(raw_response),
        "semantic": domain_commitment(RESPONSE_SEMANTIC_DOMAIN, response),
    }
    return record, validation_context, response_identity, evidence_bundle


def require_retained_kit(kit: dict[str, Any], content: bytes) -> None:
    current = read_file(OUTPUT_RELATIVE, MAX_KIT_BYTES)
    if current != content:
        fail("generated reviewer kit is missing or stale")
    parsed = parse_object(current, OUTPUT_RELATIVE, MAX_KIT_BYTES)
    if parsed != kit:
        fail("generated reviewer kit semantics differ from expected content")


def materialize_private_response(
    raw_response: bytes,
    response: dict[str, Any],
    kit: dict[str, Any],
    artifact_overrides: dict[str, bytes],
    *,
    registry_source_override: bytes | None = None,
) -> dict[str, Any]:
    (
        record,
        validation_context,
        response_identity,
        evidence_bundle,
    ) = materialize_response_value(
        response,
        kit,
        raw_response=raw_response,
        artifact_overrides=artifact_overrides,
        registry_source_override=registry_source_override,
    )
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
        raw_response,
        response_identity,
        evidence_bundle,
        candidate_schema,
        validation_context["registry_replay_inputs"],
    )
    if read_file(CANDIDATE_SCHEMA_RELATIVE, MAX_SCHEMA_BYTES) != candidate_schema_raw:
        fail("candidate schema changed during envelope validation")
    return envelope


def source_candidate_envelope(
    response: dict[str, Any],
    record: dict[str, Any],
    kit: dict[str, Any],
    validation_context: dict[str, Any],
    raw_response: bytes,
    response_identity: dict[str, Any],
    evidence_bundle: dict[str, Any],
    candidate_schema: dict[str, Any],
    expected_registry_replay_inputs: list[dict[str, str | int]],
) -> dict[str, Any]:
    exact_keys(
        validation_context,
        {
            "private_bundle_preflight",
            "bounded_json_reader",
            "immutable_git_reader",
            "schema_validator",
            "review_request",
            "review_packet",
            "reviewer_kit_generator",
            "reviewer_kit",
            "reviewer_kit_schema",
            "response_schema",
            "candidate_schema",
            "registry_generator",
            "registry_schema",
            "registry_replay_inputs",
            "validated_against_registry_source",
            "validated_against_proposed_registry",
        },
        "review source candidate validation context",
    )
    if validation_context != {
        "private_bundle_preflight": copy.deepcopy(
            kit["inputs"]["private_bundle_preflight"]
        ),
        "bounded_json_reader": copy.deepcopy(kit["inputs"]["bounded_json_reader"]),
        "immutable_git_reader": copy.deepcopy(kit["inputs"]["immutable_git_reader"]),
        "schema_validator": copy.deepcopy(kit["inputs"]["schema_validator"]),
        "review_request": copy.deepcopy(kit["inputs"]["review_request"]),
        "review_packet": copy.deepcopy(kit["subject_cut"]["review_packet"]),
        "reviewer_kit_generator": copy.deepcopy(kit["generated_by"]),
        "reviewer_kit": identity(OUTPUT_RELATIVE, generated_bytes(kit)),
        "reviewer_kit_schema": copy.deepcopy(kit["inputs"]["reviewer_kit_schema"]),
        "response_schema": copy.deepcopy(kit["inputs"]["review_response_schema"]),
        "candidate_schema": copy.deepcopy(
            kit["inputs"]["review_source_candidate_schema"]
        ),
        "registry_generator": copy.deepcopy(
            kit["inputs"]["decision_registry_generator"]
        ),
        "registry_schema": copy.deepcopy(kit["inputs"]["decision_registry_schema"]),
        "registry_replay_inputs": validation_context["registry_replay_inputs"],
        "validated_against_registry_source": validation_context[
            "validated_against_registry_source"
        ],
        "validated_against_proposed_registry": validation_context[
            "validated_against_proposed_registry"
        ],
    }:
        fail("review source candidate validation context changed fixed identities")
    validate_registry_replay_identities(validation_context["registry_replay_inputs"])
    validate_registry_replay_identities(expected_registry_replay_inputs)
    if validation_context["registry_replay_inputs"] != expected_registry_replay_inputs:
        fail("review source candidate changed its captured registry replay inputs")
    if validation_context["validated_against_registry_source"].get("path") != (
        REGISTRY_SOURCE_RELATIVE
    ):
        fail("review source candidate names another registry source")
    if validation_context["validated_against_proposed_registry"].get("path") != (
        CURRENT_PROPOSED_REGISTRY_RELATIVE
    ):
        fail("review source candidate names another proposed registry")
    expected_response_identity = {
        "raw": raw_response_identity(raw_response),
        "semantic": domain_commitment(RESPONSE_SEMANTIC_DOMAIN, response),
    }
    if response_identity != expected_response_identity:
        fail("review source candidate response identity changed")
    if evidence_bundle != evidence_bundle_projection(response):
        fail("review source candidate evidence bundle changed")
    matching_slots = [
        slot for slot in kit["slots"] if slot["slot_id"] == response.get("slot_id")
    ]
    if len(matching_slots) != 1:
        fail("review source candidate does not select exactly one kit slot")
    slot = matching_slots[0]
    subjects = {
        decision["adr_id"]: decision["subject"] for decision in kit["decisions"]
    }
    if any(record.get(name) != response.get(name) for name in HUMAN_SOURCE_MEMBERS):
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
        "admission_status": "NOT_EVALUATED",
        "claim_boundary": CANDIDATE_CLAIM_BOUNDARY,
        "slot_id": response["slot_id"],
        "subject_binding": copy.deepcopy(response["subject_binding"]),
        "response_identity": copy.deepcopy(response_identity),
        "evidence_bundle": copy.deepcopy(evidence_bundle),
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
            "admission_status",
            "claim_boundary",
            "slot_id",
            "subject_binding",
            "response_identity",
            "evidence_bundle",
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
        or envelope["admission_status"] != "NOT_EVALUATED"
        or envelope["registry_mutation"] is not False
        or envelope["external_verifier_required"] is not True
        or envelope["claim_boundary"] != CANDIDATE_CLAIM_BOUNDARY
        or set(envelope["source_record"]) != set(EXPECTED_SOURCE_FIELDS)
        or envelope["subject_binding"] != slot["subject_binding"]
        or envelope["response_identity"] != response_identity
        or envelope["evidence_bundle"] != evidence_bundle
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
        "schema": SLOT_ENVELOPE_SCHEMA,
        "normative": False,
        "authorizing": False,
        "claim_boundary": KIT_CLAIM_BOUNDARY,
        "slot": slot,
        "machine_injected_source": {
            "adr_id": slot["adr_id"],
            "role_id": slot["role_id"],
            "subject": copy.deepcopy(subjects[slot["adr_id"]]),
        },
        "required_response_transport": {
            "subject_binding": copy.deepcopy(slot["subject_binding"])
        },
        "human_response_schema": copy.deepcopy(kit["inputs"]["review_response_schema"]),
    }


def must_fail(action: Any, label: str) -> None:
    try:
        action()
    except ReviewerKitError:
        return
    fail(f"hostile reviewer-kit self-test unexpectedly passed: {label}")


def must_fail_with_text(action: Any, expected: str, label: str) -> None:
    try:
        action()
    except ReviewerKitError as error:
        if expected not in str(error):
            fail(f"hostile {label} failed for another reason: {error}")
        return
    fail(f"hostile reviewer-kit self-test unexpectedly passed: {label}")


def self_test() -> None:
    snapshots = snapshot_inputs()
    kit = build_kit_from_snapshots(snapshots)
    first_slot = kit["slots"][0]
    first_subject = kit["decisions"][0]["subject"]
    expected_subject_binding = subject_binding_value(first_slot, first_subject)
    first_slot_envelope = slot_envelope(first_slot["slot_id"], kit)
    if (
        first_slot_envelope["schema"] != SLOT_ENVELOPE_SCHEMA
        or first_slot_envelope["slot"] != first_slot
        or first_slot_envelope["required_response_transport"]
        != {"subject_binding": expected_subject_binding}
        or first_slot_envelope["human_response_schema"]
        != kit["inputs"]["review_response_schema"]
    ):
        fail("Version 2 slot envelope changed its exact review transport")

    def mutate_scalar_leaves(value: Any) -> list[Any]:
        variants: list[Any] = []
        if type(value) is dict:
            for key, member in value.items():
                for changed in mutate_scalar_leaves(member):
                    variant = copy.deepcopy(value)
                    variant[key] = changed
                    variants.append(variant)
        elif type(value) is list:
            for index, member in enumerate(value):
                for changed in mutate_scalar_leaves(member):
                    variant = copy.deepcopy(value)
                    variant[index] = changed
                    variants.append(variant)
        elif type(value) is str:
            variants.append(value + "x")
        elif type(value) is int:
            variants.append(value + 1)
        elif type(value) is bool:
            variants.append(not value)
        return variants

    for changed_subject in mutate_scalar_leaves(first_subject):
        if (
            subject_binding_value(first_slot, changed_subject)
            == expected_subject_binding
        ):
            fail("subject binding did not change after one subject-leaf mutation")
    for slot_field in SUBJECT_BINDING_SLOT_MEMBERS:
        changed_values = mutate_scalar_leaves(first_slot[slot_field])
        if not changed_values:
            fail(f"subject binding slot member {slot_field} has no scalar leaves")
        for changed in changed_values:
            changed_slot = copy.deepcopy(first_slot)
            changed_slot[slot_field] = changed
            if (
                subject_binding_value(changed_slot, first_subject)
                == expected_subject_binding
            ):
                fail(f"subject binding did not change after {slot_field} mutation")
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
    lifecycle_reader = globals()["read_file"]
    for relative in (
        PREFLIGHT_RELATIVE,
        BOUNDED_JSON_RELATIVE,
        REVIEW_PACKET_RELATIVE,
    ):

        def changed_lifecycle_input(
            requested: str,
            maximum_bytes: int,
            *,
            changed_relative: str = relative,
        ) -> bytes:
            raw = lifecycle_reader(requested, maximum_bytes)
            return raw + b" " if requested == changed_relative else raw

        globals()["read_file"] = changed_lifecycle_input
        try:
            must_fail(
                lambda: validate_current_review_capture(kit),
                f"review-capture fixed input drift for {relative}",
            )
        finally:
            globals()["read_file"] = lifecycle_reader
    isolated_zero_source = parse_object(
        read_file(REGISTRY_SOURCE_RELATIVE, MAX_INPUT_BYTES),
        REGISTRY_SOURCE_RELATIVE,
        MAX_INPUT_BYTES,
    )
    isolated_zero_source["review_records"] = []
    isolated_zero_source_bytes = generated_bytes(isolated_zero_source)
    isolated_zero_source = parse_object(
        isolated_zero_source_bytes,
        "isolated zero-review registry source",
        MAX_INPUT_BYTES,
    )
    isolated_repository_snapshots, isolated_evidence_snapshots = (
        snapshot_registry_replay_inputs(isolated_zero_source)
    )
    budget_reader_calls: list[str] = []

    def bounded_budget_reader(relative: str, maximum_bytes: int) -> bytes:
        budget_reader_calls.append(relative)
        if maximum_bytes < 2:
            fail("aggregate replay budget reached the reader")
        return b"xx"

    must_fail(
        lambda: snapshot_registry_replay_paths(
            ("docs/adr/budget-a.md", "docs/adr/budget-b.md", "docs/adr/budget-c.md"),
            set(),
            private_evidence_paths=frozenset(),
            reader=bounded_budget_reader,
            maximum_total_bytes=4,
        ),
        "registry replay aggregate budget exhaustion",
    )
    if budget_reader_calls != ["docs/adr/budget-a.md", "docs/adr/budget-b.md"]:
        fail("registry replay opened a file after exhausting its aggregate budget")
    with tempfile.TemporaryDirectory(prefix="ncp-b01-promotion-absence-") as temporary:
        promotion_probe = Path(temporary) / "decision-registry.v1.json"
        require_absent_promotion_target(promotion_probe)
        promotion_probe.write_bytes(b"forbidden\n")
        must_fail(
            lambda: require_absent_promotion_target(promotion_probe),
            "present non-normative promotion target",
        )
        promotion_probe.unlink()
        promotion_probe.symlink_to("missing-target")
        must_fail(
            lambda: require_absent_promotion_target(promotion_probe),
            "dangling promotion-target symlink",
        )

    missing_repository_snapshot = dict(isolated_repository_snapshots)
    missing_repository_snapshot.pop(next(iter(missing_repository_snapshot)))
    must_fail(
        lambda: execute_exact_registry_generator(
            snapshots[REGISTRY_GENERATOR_RELATIVE],
            isolated_zero_source,
            artifact_overrides=isolated_evidence_snapshots,
            immutable_git_source=snapshots[IMMUTABLE_GIT_RELATIVE],
            bounded_json_source=snapshots[BOUNDED_JSON_RELATIVE],
            schema_validator_source=snapshots[SCHEMA_VALIDATOR_RELATIVE],
            repository_snapshots=missing_repository_snapshot,
        ),
        "missing exact registry repository input",
    )
    extra_repository_snapshot = dict(isolated_repository_snapshots)
    extra_repository_snapshot["docs/adr/attacker-input.md"] = b"attacker\n"
    must_fail(
        lambda: execute_exact_registry_generator(
            snapshots[REGISTRY_GENERATOR_RELATIVE],
            isolated_zero_source,
            artifact_overrides=isolated_evidence_snapshots,
            immutable_git_source=snapshots[IMMUTABLE_GIT_RELATIVE],
            bounded_json_source=snapshots[BOUNDED_JSON_RELATIVE],
            schema_validator_source=snapshots[SCHEMA_VALIDATOR_RELATIVE],
            repository_snapshots=extra_repository_snapshot,
        ),
        "extra exact registry repository input",
    )
    changed_schema_repository = dict(isolated_repository_snapshots)
    changed_schema_repository[REGISTRY_SCHEMA_RELATIVE] += b" "
    must_fail(
        lambda: execute_exact_registry_generator(
            snapshots[REGISTRY_GENERATOR_RELATIVE],
            isolated_zero_source,
            artifact_overrides=isolated_evidence_snapshots,
            immutable_git_source=snapshots[IMMUTABLE_GIT_RELATIVE],
            bounded_json_source=snapshots[BOUNDED_JSON_RELATIVE],
            schema_validator_source=snapshots[SCHEMA_VALIDATOR_RELATIVE],
            repository_snapshots=changed_schema_repository,
        ),
        "co-mutated exact registry schema",
    )
    must_fail(
        lambda: execute_exact_registry_generator(
            snapshots[REGISTRY_GENERATOR_RELATIVE],
            isolated_zero_source,
            artifact_overrides={"evidence/implementation/reviews/B01/extra.json": b"x"},
            immutable_git_source=snapshots[IMMUTABLE_GIT_RELATIVE],
            bounded_json_source=snapshots[BOUNDED_JSON_RELATIVE],
            schema_validator_source=snapshots[SCHEMA_VALIDATOR_RELATIVE],
            repository_snapshots=isolated_repository_snapshots,
        ),
        "extra exact registry evidence input",
    )
    for label, injected_call, expected_error in (
        (
            "unbound bounded registry read",
            (
                'read_bounded_regular_file(ROOT / "docs/adr/unbound.json", '
                'limits=REGISTRY_FILE_LIMITS, label="unbound bounded self-test")'
            ),
            "requested an unbound bounded input",
        ),
        (
            "unbound repository registry read",
            (
                'read_repository_regular_file("docs/adr/unbound.md", '
                'maximum_bytes=1, label="unbound repository self-test")'
            ),
            "requested an unbound repository input",
        ),
    ):
        altered_generator = (
            snapshots[REGISTRY_GENERATOR_RELATIVE]
            + (
                "\n_ncp_original_build_registry = build_registry\n"
                "def build_registry(*args, **kwargs):\n"
                f"    {injected_call}\n"
                "    return _ncp_original_build_registry(*args, **kwargs)\n"
            ).encode()
        )
        altered_repository = dict(isolated_repository_snapshots)
        altered_repository[REGISTRY_GENERATOR_RELATIVE] = altered_generator
        must_fail_with_text(
            lambda source=altered_generator, repository=altered_repository: (
                execute_exact_registry_generator(
                    source,
                    isolated_zero_source,
                    artifact_overrides=isolated_evidence_snapshots,
                    immutable_git_source=snapshots[IMMUTABLE_GIT_RELATIVE],
                    bounded_json_source=snapshots[BOUNDED_JSON_RELATIVE],
                    schema_validator_source=snapshots[SCHEMA_VALIDATOR_RELATIVE],
                    repository_snapshots=repository,
                )
            ),
            expected_error,
            label,
        )

    ambient_helper_calls: list[str] = []

    def ambient_helper_called(name: str) -> NoReturn:
        ambient_helper_calls.append(name)
        fail(f"ambient helper executed: {name}")

    ambient_bounded = types.ModuleType("bounded_json")
    ambient_bounded.BoundedJsonError = RuntimeError
    for name in (
        "FileSnapshotLimits",
        "JsonLimits",
        "parse_json_bytes",
        "read_bounded_regular_file",
        "validate_native_json_tree",
    ):
        setattr(
            ambient_bounded,
            name,
            lambda *_args, _name=name, **_kwargs: ambient_helper_called(_name),
        )
    ambient_validator = types.ModuleType("validate_evidence_schemas")
    ambient_validator.EvidenceSchemaError = RuntimeError
    for name in ("validate_decision_registry_instance", "validate_instance"):
        setattr(
            ambient_validator,
            name,
            lambda *_args, _name=name, **_kwargs: ambient_helper_called(_name),
        )
    prior_bounded = sys.modules.get("bounded_json")
    prior_validator = sys.modules.get("validate_evidence_schemas")
    sys.modules["bounded_json"] = ambient_bounded
    sys.modules["validate_evidence_schemas"] = ambient_validator
    with tempfile.TemporaryDirectory(prefix="ncp-b01-fake-git-") as temporary:
        fake_directory = Path(temporary)
        fake_git = fake_directory / "git"
        marker = fake_directory / "original-resolver-executed"
        fake_git.write_bytes(b'#!/bin/sh\n: > "$NCP_B01_FAKE_GIT_MARKER"\nexit 99\n')
        fake_git.chmod(0o700)
        original_path = os.environ.get("PATH")
        original_marker = os.environ.get("NCP_B01_FAKE_GIT_MARKER")
        os.environ["PATH"] = (
            f"{fake_directory}{os.pathsep}{original_path}"
            if original_path is not None
            else str(fake_directory)
        )
        os.environ["NCP_B01_FAKE_GIT_MARKER"] = str(marker)
        try:
            isolated_zero_generated, isolated_zero_registry_bytes = (
                execute_exact_registry_generator(
                    snapshots[REGISTRY_GENERATOR_RELATIVE],
                    isolated_zero_source,
                    artifact_overrides=isolated_evidence_snapshots,
                    immutable_git_source=snapshots[IMMUTABLE_GIT_RELATIVE],
                    bounded_json_source=snapshots[BOUNDED_JSON_RELATIVE],
                    schema_validator_source=snapshots[SCHEMA_VALIDATOR_RELATIVE],
                    repository_snapshots=isolated_repository_snapshots,
                )
            )
            if (
                sys.modules.get("bounded_json") is not ambient_bounded
                or sys.modules.get("validate_evidence_schemas") is not ambient_validator
            ):
                fail("exact registry replay did not restore ambient helper modules")
            must_fail(
                lambda: execute_exact_registry_generator(
                    snapshots[REGISTRY_GENERATOR_RELATIVE],
                    isolated_zero_source,
                    artifact_overrides=isolated_evidence_snapshots,
                    immutable_git_source=snapshots[IMMUTABLE_GIT_RELATIVE],
                    bounded_json_source=snapshots[BOUNDED_JSON_RELATIVE],
                    schema_validator_source=b'raise ImportError("hostile self-test")\n',
                    repository_snapshots=isolated_repository_snapshots,
                ),
                "exact helper ImportError normalization",
            )
            if (
                sys.modules.get("bounded_json") is not ambient_bounded
                or sys.modules.get("validate_evidence_schemas") is not ambient_validator
            ):
                fail("failed exact replay did not restore ambient helper modules")
        finally:
            if original_path is None:
                del os.environ["PATH"]
            else:
                os.environ["PATH"] = original_path
            if original_marker is None:
                del os.environ["NCP_B01_FAKE_GIT_MARKER"]
            else:
                os.environ["NCP_B01_FAKE_GIT_MARKER"] = original_marker
            if prior_bounded is None:
                sys.modules.pop("bounded_json", None)
            else:
                sys.modules["bounded_json"] = prior_bounded
            if prior_validator is None:
                sys.modules.pop("validate_evidence_schemas", None)
            else:
                sys.modules["validate_evidence_schemas"] = prior_validator
        if marker.exists():
            fail("exact registry replay executed the PATH-selected Git resolver")
    if ambient_helper_calls:
        fail("exact registry replay executed an ambient helper module")
    if (
        review_capture_phase_value(isolated_zero_source, isolated_zero_generated)
        != ZERO_REVIEW_ISSUANCE
    ):
        fail("isolated zero-review source selected another lifecycle phase")
    registry_schema = parse_object(
        snapshots[REGISTRY_SCHEMA_RELATIVE],
        REGISTRY_SCHEMA_RELATIVE,
        MAX_INPUT_BYTES,
    )
    malformed_registry = copy.deepcopy(isolated_zero_generated)
    malformed_registry["attacker_field"] = True
    must_fail(
        lambda: schema_validate(
            registry_schema,
            malformed_registry,
            "malformed exact replay registry",
            REGISTRY_SCHEMA_ID,
        ),
        "exact replay output outside the bound registry schema",
    )
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
        "subject_binding": copy.deepcopy(kit["slots"][0]["subject_binding"]),
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
    for label, character in (
        ("NUL", "\x00"),
        ("newline", "\n"),
        ("DEL", "\x7f"),
    ):
        hostile_path = copy.deepcopy(response_fixture)
        hostile_path["role_authorization"]["path"] = (
            f"{EVIDENCE_PREFIX}hostile{character}path.json"
        )
        must_fail(
            lambda value=hostile_path: schema_validate(
                response_schema,
                value,
                "hostile response evidence path",
                RESPONSE_SCHEMA_ID,
            ),
            f"response evidence path containing {label}",
        )
    aliased_evidence = copy.deepcopy(response_fixture)
    aliased_evidence["external_receipt"] = copy.deepcopy(
        aliased_evidence["role_authorization"]
    )
    must_fail(
        lambda: evidence_bundle_projection(aliased_evidence),
        "one file aliased across required evidence roles",
    )
    must_fail(
        lambda: materialize_response_value(
            response_fixture,
            kit,
            raw_response=generated_bytes(response_fixture),
            artifact_overrides={
                response_fixture["role_authorization"]["path"]: role_bytes,
                response_fixture["external_receipt"]["path"]: receipt_bytes,
            },
            registry_source_override=generated_bytes(maximum_phase_source),
        ),
        "257th bounded review materialization",
    )
    must_fail(
        lambda: materialize_response_value(
            response_fixture,
            kit,
            raw_response=generated_bytes(response_fixture),
            artifact_overrides={
                response_fixture["role_authorization"]["path"]: role_bytes,
                response_fixture["external_receipt"]["path"]: receipt_bytes,
            },
            registry_source_override=isolated_zero_source_bytes,
            proposed_registry_override=b'{"stale":true}\n',
        ),
        "registry source/proposed race before materialization",
    )
    injected_module = types.ModuleType("generate_decision_registry")
    injected_module.build_registry = lambda *_args, **_kwargs: {"review_records": []}
    prior_module = sys.modules.get("generate_decision_registry")
    sys.modules["generate_decision_registry"] = injected_module
    try:
        (
            candidate,
            candidate_context,
            candidate_response_identity,
            candidate_evidence_bundle,
        ) = materialize_response_value(
            response_fixture,
            evolved_registry_kit,
            raw_response=generated_bytes(response_fixture),
            artifact_overrides={
                response_fixture["role_authorization"]["path"]: role_bytes,
                response_fixture["external_receipt"]["path"]: receipt_bytes,
            },
            registry_source_override=isolated_zero_source_bytes,
            proposed_registry_override=isolated_zero_registry_bytes,
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
    one_record_generated, one_record_bytes = execute_exact_registry_generator(
        snapshots[REGISTRY_GENERATOR_RELATIVE],
        one_record_source,
        artifact_overrides={
            response_fixture["role_authorization"]["path"]: role_bytes,
            response_fixture["external_receipt"]["path"]: receipt_bytes,
        },
        immutable_git_source=snapshots[IMMUTABLE_GIT_RELATIVE],
        bounded_json_source=snapshots[BOUNDED_JSON_RELATIVE],
        schema_validator_source=snapshots[SCHEMA_VALIDATOR_RELATIVE],
        repository_snapshots=isolated_repository_snapshots,
    )
    if (
        review_capture_phase_value(one_record_source, one_record_generated)
        != REVIEW_CAPTURE_ACTIVE
    ):
        fail("one valid review did not activate the review-capture phase")
    original_collision_reader = globals()["read_file"]
    collision_evidence = {
        response_fixture["role_authorization"]["path"]: role_bytes,
        response_fixture["external_receipt"]["path"]: receipt_bytes,
    }
    collision_reads: set[str] = set()

    def collision_reader(relative: str, maximum_bytes: int) -> bytes:
        raw = collision_evidence.get(relative)
        if raw is None:
            return original_collision_reader(relative, maximum_bytes)
        if len(raw) > maximum_bytes:
            fail("collision fixture exceeded its requested read bound")
        collision_reads.add(relative)
        return raw

    globals()["read_file"] = collision_reader
    try:
        must_fail_with_text(
            lambda: materialize_response_value(
                response_fixture,
                kit,
                raw_response=generated_bytes(response_fixture),
                artifact_overrides=collision_evidence,
                registry_source_override=generated_bytes(one_record_source),
                proposed_registry_override=one_record_bytes,
            ),
            "private response evidence reuses an existing registry evidence path",
            "private evidence path reused by the current registry",
        )
    finally:
        globals()["read_file"] = original_collision_reader
    if collision_reads != set(collision_evidence):
        fail("private/current evidence collision control missed current evidence reads")
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
        generated_bytes(response_fixture),
        candidate_response_identity,
        candidate_evidence_bundle,
        candidate_schema,
        candidate_context["registry_replay_inputs"],
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
    for label, path in (
        ("raw response digest", ("response_identity", "raw", "sha256")),
        ("semantic response digest", ("response_identity", "semantic", "sha256")),
        ("evidence bundle digest", ("evidence_bundle", "files", 0, "sha256")),
    ):
        hostile_envelope = copy.deepcopy(envelope)
        target: Any = hostile_envelope
        for component in path[:-1]:
            target = target[component]
        target[path[-1]] = "0" * 64
        must_fail(
            lambda value=hostile_envelope: source_candidate_envelope(
                response_fixture,
                candidate,
                kit,
                candidate_context,
                generated_bytes(response_fixture),
                value["response_identity"],
                value["evidence_bundle"],
                candidate_schema,
                candidate_context["registry_replay_inputs"],
            ),
            f"candidate {label} substitution",
        )
    hostile_response = copy.deepcopy(response_fixture)
    hostile_response["subject_binding"]["sha256"] = "0" * 64
    must_fail(
        lambda: source_candidate_envelope(
            hostile_response,
            candidate,
            kit,
            candidate_context,
            generated_bytes(hostile_response),
            {
                "raw": raw_response_identity(generated_bytes(hostile_response)),
                "semantic": domain_commitment(
                    RESPONSE_SEMANTIC_DOMAIN, hostile_response
                ),
            },
            candidate_evidence_bundle,
            candidate_schema,
            candidate_context["registry_replay_inputs"],
        ),
        "candidate subject binding substitution",
    )
    for context_name in (
        "private_bundle_preflight",
        "bounded_json_reader",
        "immutable_git_reader",
        "schema_validator",
        "review_request",
        "review_packet",
        "reviewer_kit_generator",
        "reviewer_kit",
        "reviewer_kit_schema",
        "response_schema",
        "candidate_schema",
        "registry_generator",
        "registry_schema",
    ):
        hostile_context = copy.deepcopy(candidate_context)
        hostile_context[context_name]["sha256"] = "0" * 64
        must_fail(
            lambda value=hostile_context: source_candidate_envelope(
                response_fixture,
                candidate,
                kit,
                value,
                generated_bytes(response_fixture),
                candidate_response_identity,
                candidate_evidence_bundle,
                candidate_schema,
                candidate_context["registry_replay_inputs"],
            ),
            f"candidate {context_name} identity drift",
        )
    hostile_context = copy.deepcopy(candidate_context)
    hostile_context["registry_replay_inputs"][0]["sha256"] = "0" * 64
    must_fail(
        lambda: source_candidate_envelope(
            response_fixture,
            candidate,
            kit,
            hostile_context,
            generated_bytes(response_fixture),
            candidate_response_identity,
            candidate_evidence_bundle,
            candidate_schema,
            candidate_context["registry_replay_inputs"],
        ),
        "candidate registry replay digest drift",
    )
    hostile_context = copy.deepcopy(candidate_context)
    hostile_context["registry_replay_inputs"] = hostile_context[
        "registry_replay_inputs"
    ][:-1]
    must_fail(
        lambda: source_candidate_envelope(
            response_fixture,
            candidate,
            kit,
            hostile_context,
            generated_bytes(response_fixture),
            candidate_response_identity,
            candidate_evidence_bundle,
            candidate_schema,
            candidate_context["registry_replay_inputs"],
        ),
        "candidate missing registry replay input",
    )
    hostile_context = copy.deepcopy(candidate_context)
    (
        hostile_context["registry_replay_inputs"][0],
        hostile_context["registry_replay_inputs"][1],
    ) = (
        hostile_context["registry_replay_inputs"][1],
        hostile_context["registry_replay_inputs"][0],
    )
    must_fail(
        lambda: source_candidate_envelope(
            response_fixture,
            candidate,
            kit,
            hostile_context,
            generated_bytes(response_fixture),
            candidate_response_identity,
            candidate_evidence_bundle,
            candidate_schema,
            candidate_context["registry_replay_inputs"],
        ),
        "candidate reordered registry replay inputs",
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
            generated_bytes(response_fixture),
            candidate_response_identity,
            candidate_evidence_bundle,
            candidate_schema,
            candidate_context["registry_replay_inputs"],
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
            generated_bytes(hostile_response),
            candidate_response_identity,
            candidate_evidence_bundle,
            candidate_schema,
            candidate_context["registry_replay_inputs"],
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
            generated_bytes(response_fixture),
            candidate_response_identity,
            candidate_evidence_bundle,
            candidate_schema,
            candidate_context["registry_replay_inputs"],
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
            generated_bytes(response_fixture),
            candidate_response_identity,
            candidate_evidence_bundle,
            candidate_schema,
            candidate_context["registry_replay_inputs"],
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
                raw_response=generated_bytes(response_fixture),
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
            immutable_git_source=snapshots[IMMUTABLE_GIT_RELATIVE],
            bounded_json_source=snapshots[BOUNDED_JSON_RELATIVE],
            schema_validator_source=snapshots[SCHEMA_VALIDATOR_RELATIVE],
            repository_snapshots=isolated_repository_snapshots,
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
            raw_response=generated_bytes(hostile_response),
            artifact_overrides={
                hostile_response["role_authorization"]["path"]: role_bytes,
                hostile_response["external_receipt"]["path"]: receipt_bytes,
            },
            registry_source_override=isolated_zero_source_bytes,
            proposed_registry_override=isolated_zero_registry_bytes,
        ),
        "unknown review supersession",
    )
    independent_fixture = copy.deepcopy(response_fixture)
    independent_slot = next(
        slot for slot in kit["slots"] if slot["requires_independence"]
    )
    independent_fixture["slot_id"] = independent_slot["slot_id"]
    independent_fixture["subject_binding"] = copy.deepcopy(
        independent_slot["subject_binding"]
    )
    independent_fixture["review_id"] = "honest-nonindependent-rejection"
    nonqualifying, _, _, _ = materialize_response_value(
        independent_fixture,
        kit,
        raw_response=generated_bytes(independent_fixture),
        artifact_overrides={
            independent_fixture["role_authorization"]["path"]: role_bytes,
            independent_fixture["external_receipt"]["path"]: receipt_bytes,
        },
        registry_source_override=isolated_zero_source_bytes,
        proposed_registry_override=isolated_zero_registry_bytes,
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
        raw_response=generated_bytes(independent_fixture),
        artifact_overrides={
            independent_fixture["role_authorization"]["path"]: role_bytes,
            independent_fixture["external_receipt"]["path"]: receipt_bytes,
        },
        registry_source_override=isolated_zero_source_bytes,
        proposed_registry_override=isolated_zero_registry_bytes,
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
    qualifying, _, _, _ = materialize_response_value(
        qualifying_fixture,
        kit,
        raw_response=generated_bytes(qualifying_fixture),
        artifact_overrides={
            qualifying_fixture["role_authorization"]["path"]: role_bytes,
            qualifying_fixture["external_receipt"]["path"]: receipt_bytes,
            qualifying_fixture["independence_assessment"]["path"]: assessment_bytes,
        },
        registry_source_override=isolated_zero_source_bytes,
        proposed_registry_override=isolated_zero_registry_bytes,
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
