#!/usr/bin/env python3
"""Coordinate two quarantined ADR-example semantic implementations.

This module verifies bounded source identity and exact result parity. It contains
no ADR profile rules and grants no ADR acceptance, wire admission, conformance,
interoperability, external-evidence, or release claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from bounded_json_support import BoundedJsonError, JsonLimits, parse_json_bytes
from source_inventory import SourceInventoryError, read_bounded_relative_file

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
HARNESS_ROOT = ROOT / "adr-example-semantics"
CORPUS_RELATIVE_PATH = (
    "prototypes/b01-architecture-evidence/adr-example-semantics/corpus.v1.json"
)
CORPUS_PATH = REPOSITORY / CORPUS_RELATIVE_PATH
RUST_MANIFEST = HARNESS_ROOT / "rust" / "Cargo.toml"
TYPESCRIPT_ROOT = HARNESS_ROOT / "typescript"
TYPESCRIPT_MAIN = TYPESCRIPT_ROOT / "src" / "main.ts"

CORPUS_SCHEMA = "ncp.b01-adr-example-semantics-corpus.v1"
ENGINE_RESULT_SCHEMA = "ncp.b01-adr-example-semantics-result.v1"
COORDINATOR_RESULT_SCHEMA = "ncp.b01-adr-example-semantics-coordinator-result.v1"
REVIEW_PACKET_LIFECYCLE_SCHEMA = "ncp.b01-review-packet-lifecycle.v1"
ADR_SOURCE_SET_SCHEMA = "ncp.b01-adr-source-set.v1"
ADR_SOURCE_SET_DIGEST_ALGORITHM = (
    "sha256(domain || u64be(projection_bytes) || projection)"
)
ADR_SOURCE_SET_DOMAIN_HEX = "6e63702e6230312d6164722d736f757263652d7365742e763100"
SEMANTIC_CLAIM = "local-prototype-only"
MAX_CORPUS_BYTES = 262_144
MAX_ENGINE_OUTPUT_BYTES = 262_144
MAX_ENGINE_STDERR_BYTES = 65_536
MAX_DECISION_REGISTRY_BYTES = MAX_CORPUS_BYTES
MAX_ADR_BYTES = 262_144
MAX_AGGREGATE_ADR_BYTES = 2_097_152
MAX_JSON_FENCE_BYTES = 131_072
MAX_FIXTURE_BYTES = 16_384
MAX_ENGINE_SOURCE_BYTES = 262_144
MAX_AGGREGATE_ENGINE_SOURCE_BYTES = 2_097_152
MAX_ADR_MODULES_PER_DECISION = 8
MAX_MUTATION_PURPOSE_BYTES = 512
MAX_PATCH_PATH_BYTES = 512
EXPECTED_CASE_COUNT = 25
EXPECTED_ENGINE_SELF_TEST_COUNTS = {"rust": 29, "typescript": 47}
EXPECTED_DIAGNOSTIC_REGISTRY_COUNT = 107
EXPECTED_DIAGNOSTIC_REGISTRY_BYTE_LENGTH = 3_543
EXPECTED_DIAGNOSTIC_REGISTRY_SHA256 = (
    "f8e704286f7a0c30b6525e5835bcf2d46e21e5c1bc8db7bbef928cff17208d2d"
)
EXPECTED_ADR_IDS = tuple(f"ADR-{index:03d}" for index in range(1, 12))
EXPECTED_CASE_IDENTITIES = {
    "adr001.open-plant-session.kind-separation.v1": (
        "ADR001_PLANT_KIND_SEPARATION_FRAGMENT_V1",
        "PROPOSED_WIRE_FRAGMENT",
        "POSITIVE",
        "ADR-001",
        1,
    ),
    "adr001.plant-session.simulation-field-confusion.v1": (
        "ADR001_PLANT_KIND_SEPARATION_FRAGMENT_V1",
        "PROPOSED_WIRE_FRAGMENT",
        "NEGATIVE",
        "ADR-001",
        2,
    ),
    "adr002.realm-bound-contract-identity.v1": (
        "ADR002_REALM_BOUND_CONTRACT_IDENTITY_V1",
        "PROPOSED_WIRE_FRAGMENT",
        "POSITIVE",
        "ADR-002",
        1,
    ),
    "adr002.compact-hash-substitution.v1": (
        "ADR002_REALM_BOUND_CONTRACT_IDENTITY_V1",
        "PROPOSED_WIRE_FRAGMENT",
        "NEGATIVE",
        "ADR-002",
        2,
    ),
    "adr003.flattened-jws-placeholder.v1": (
        "ADR003_FLATTENED_FORWARDING_WRAPPER_V1",
        "AUTHENTICATED_WIRE_OBJECT",
        "NEGATIVE",
        "ADR-003",
        1,
    ),
    "adr003.protected-header-required-member-projection.v1": (
        "ADR003_PROTECTED_HEADER_REQUIRED_MEMBER_PROJECTION_V1",
        "DECODED_HEADER_FRAGMENT",
        "POSITIVE",
        "ADR-003",
        2,
    ),
    "adr003.unauthenticated-forwarding-wrapper.v1": (
        "ADR003_FLATTENED_FORWARDING_WRAPPER_V1",
        "AUTHENTICATED_WIRE_OBJECT",
        "NEGATIVE",
        "ADR-003",
        3,
    ),
    "adr004.pending-release-reservation-nonallocation.v1": (
        "ADR004_PENDING_RELEASE_RESERVATION_NONALLOCATION_V1",
        "NON_WIRE_INTERNAL_STATE",
        "POSITIVE",
        "ADR-004",
        1,
    ),
    "adr005.declare-stream.excerpt.v1": (
        "ADR005_DECLARE_STREAM_EXCERPT_V1",
        "PROPOSED_WIRE_FRAGMENT",
        "POSITIVE",
        "ADR-005",
        1,
    ),
    "adr005.undeclared-frame.hostile.v1": (
        "ADR005_UNDECLARED_FRAME_V1",
        "PROPOSED_WIRE_FRAGMENT",
        "NEGATIVE",
        "ADR-005",
        2,
    ),
    "adr006.body-lease.excerpt.v1": (
        "ADR006_BODY_LEASE_EXCERPT_V1",
        "PROPOSED_WIRE_FRAGMENT",
        "POSITIVE",
        "ADR-006",
        1,
    ),
    "adr006.self-issued-stale-lease.hostile.v1": (
        "ADR006_STALE_SELF_ISSUED_LEASE_V1",
        "PROPOSED_WIRE_FRAGMENT",
        "NEGATIVE",
        "ADR-006",
        2,
    ),
    "adr007.disposition-query.semantic-projection.v1": (
        "ADR007_DISPOSITION_QUERY_PROJECTION_V1",
        "PROPOSED_SEMANTIC_PROJECTION",
        "POSITIVE",
        "ADR-007",
        1,
    ),
    "adr007.received-disposition.excerpt.v1": (
        "ADR007_RECEIVED_DISPOSITION_EXCERPT_V1",
        "PROPOSED_WIRE_FRAGMENT",
        "POSITIVE",
        "ADR-007",
        2,
    ),
    "adr007.unknown-disposition.hostile.v1": (
        "ADR007_INVALID_DISPOSITION_V1",
        "PROPOSED_WIRE_FRAGMENT",
        "NEGATIVE",
        "ADR-007",
        3,
    ),
    "adr008.raw-chunk.semantic-projection.v1": (
        "ADR008_RAW_CHUNK_PROJECTION_V1",
        "PROPOSED_SEMANTIC_PROJECTION",
        "POSITIVE",
        "ADR-008",
        1,
    ),
    "adr008.evaluated-envelope.excerpt.v1": (
        "ADR008_GALADRIEL_ASSESSMENT_ENVELOPE_V1",
        "PROPOSED_EXTENSION_ENVELOPE",
        "POSITIVE",
        "ADR-008",
        2,
    ),
    "adr008.self-policy.hostile.v1": (
        "ADR008_GALADRIEL_POLICY_INJECTION_V1",
        "PROPOSED_EXTENSION_ENVELOPE",
        "NEGATIVE",
        "ADR-008",
        3,
    ),
    "adr009.security-state.semantic-projection.v1": (
        "ADR009_SECURITY_STATE_PROJECTION_V1",
        "PROPOSED_SEMANTIC_PROJECTION",
        "POSITIVE",
        "ADR-009",
        1,
    ),
    "adr009.ambiguous-mutable-security-state.hostile.v1": (
        "ADR009_INVALID_SECURITY_STATE_V1",
        "PROPOSED_SEMANTIC_PROJECTION",
        "NEGATIVE",
        "ADR-009",
        2,
    ),
    "adr010.action-qos-profile.excerpt.v1": (
        "ADR010_ACTION_QOS_PROFILE_V1",
        "PROPOSED_SEMANTIC_PROJECTION",
        "POSITIVE",
        "ADR-010",
        1,
    ),
    "adr010.best-effort-receipt-free-profile.hostile.v1": (
        "ADR010_INVALID_ACTION_QOS_PROFILE_V1",
        "PROPOSED_SEMANTIC_PROJECTION",
        "NEGATIVE",
        "ADR-010",
        2,
    ),
    "adr011.gated-intent-correlation.excerpt.v1": (
        "ADR011_GATED_INTENT_CORRELATION_EXCERPT_V1",
        "NON_NCP_INTENT_CORRELATION_FRAGMENT",
        "POSITIVE",
        "ADR-011",
        1,
    ),
    "adr011.identity-laundering-command.hostile.v1": (
        "ADR011_COMMAND_IDENTITY_AUTHORITY_SEPARATION_V1",
        "PROPOSED_WIRE_FRAGMENT",
        "NEGATIVE",
        "ADR-011",
        2,
    ),
    "adr011.effect-path-fencing.semantic-projection.v1": (
        "ADR011_EFFECT_PATH_FENCING_PROJECTION_V1",
        "PROPOSED_SEMANTIC_PROJECTION",
        "POSITIVE",
        "ADR-011",
        3,
    ),
}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
ADR_MAIN_PATH = re.compile(
    r"docs/adr/(000[1-9]|001[01])-[a-z0-9]+(?:-[a-z0-9]+)*\.md\Z"
)
ADR_MODULE_PATH = re.compile(
    r"docs/adr/modules/adr-(00[1-9]|01[01])-[a-z0-9]+(?:-[a-z0-9]+)*\.md\Z"
)
CASE_ID = re.compile(r"[a-z0-9][a-z0-9.-]*\.v1\Z")
PROFILE_ID = re.compile(r"ADR(?:00[1-9]|01[01])_[A-Z0-9_]+_V1\Z")
DIAGNOSTIC_ID = re.compile(r"[A-Z][A-Z0-9_]*\Z")

EXPECTED_LIMITS = {
    "maximum_corpus_bytes": MAX_CORPUS_BYTES,
    "maximum_aggregate_adr_bytes": MAX_AGGREGATE_ADR_BYTES,
    "maximum_adr_bytes": MAX_ADR_BYTES,
    "maximum_json_fence_bytes": MAX_JSON_FENCE_BYTES,
    "maximum_fixture_bytes": MAX_FIXTURE_BYTES,
    "maximum_json_depth": 32,
    "maximum_json_nodes": 100_000,
    "maximum_object_members": 4_096,
    "maximum_array_items": 4_096,
    "maximum_key_utf8_bytes": 128,
    "maximum_string_utf8_bytes": 65_536,
    "maximum_total_string_utf8_bytes": 131_072,
    "maximum_integer_characters": 32,
    "allow_floats": False,
    "expected_case_count": EXPECTED_CASE_COUNT,
    "expected_mutation_count": 132,
    "minimum_mutations_per_case": 2,
    "maximum_mutations_per_case": 24,
    "maximum_engine_output_bytes": MAX_ENGINE_OUTPUT_BYTES,
    "engine_timeout_seconds": 120,
}
EXPECTED_CLOSED_VALUES = {
    "scope": [
        "AUTHENTICATED_WIRE_OBJECT",
        "DECODED_HEADER_FRAGMENT",
        "NON_NCP_INTENT_CORRELATION_FRAGMENT",
        "NON_WIRE_INTERNAL_STATE",
        "PROPOSED_EXTENSION_ENVELOPE",
        "PROPOSED_SEMANTIC_PROJECTION",
        "PROPOSED_WIRE_FRAGMENT",
    ],
    "polarity": ["NEGATIVE", "POSITIVE"],
    "profile_result": [
        "MATCH_NON_AUTHORIZING_EXCERPT",
        "MATCH_NON_WIRE_EXCERPT",
        "REJECT",
    ],
    "production_admission": ["NOT_APPLICABLE", "NOT_EVALUATED", "REJECT"],
    "patch_target": ["BOUNDED_FIXTURE", "DOCUMENT"],
    "patch_operation": ["ADD", "REMOVE", "REPLACE"],
}
EXPECTED_CLAIM_BOUNDARY_KEYS = {
    "adrs_accepted",
    "normative_contract_changed",
    "production_admission_implemented",
    "interoperability_established",
    "independent_evidence_satisfied",
    "external_gate_satisfied",
    "release_authorized",
}
EXPECTED_SOURCE_BINDING = {
    "fence_language": "json",
    "fence_capture": (
        "content_between_top_level_exact_json_fence_lines_excluding_one_terminal_line_ending"
    ),
    "path_root": "repository",
    "sha256_encoding": "lowercase_hex",
}
EXPECTED_DECISION_SET_RECIPE = {
    "schema": "ncp.b01-decision-set.v1",
    "registry_path": "docs/adr/decision-registry.proposed.v1.json",
    "digest_algorithm": ("sha256(domain || u64be(projection_bytes) || projection)"),
    "domain_hex": "6e63702e6230312d6465636973696f6e2d7365742e763100",
    "projection_encoding": "UTF8_JSON_SORTED_KEYS_COMPACT_ENSURE_ASCII_FALSE",
    "projection_members": [
        "schema",
        "candidate",
        "wire_version",
        "review_policy",
        "semantic_closure",
        "decisions",
    ],
    "decision_members": [
        "id",
        "title",
        "path",
        "module_paths",
        "content_sha256",
        "bytes",
        "source_set",
        "required_reviews",
        "defect_ids",
    ],
    "effect": "NON_ACCEPTING_EXACT_SUBJECT_BINDING_ONLY",
}

CORPUS_JSON_LIMITS = JsonLimits(
    maximum_bytes=MAX_CORPUS_BYTES,
    maximum_depth=32,
    maximum_items=100_000,
    maximum_object_members=4_096,
    maximum_array_items=4_096,
    maximum_key_utf8_bytes=128,
    maximum_string_utf8_bytes=65_536,
    maximum_total_string_utf8_bytes=EXPECTED_LIMITS["maximum_total_string_utf8_bytes"],
    maximum_integer_chars=32,
    maximum_float_chars=32,
    allow_floats=False,
)
ENGINE_OUTPUT_JSON_LIMITS = JsonLimits(
    maximum_bytes=MAX_ENGINE_OUTPUT_BYTES,
    maximum_depth=32,
    maximum_items=100_000,
    maximum_object_members=4_096,
    maximum_array_items=4_096,
    maximum_key_utf8_bytes=128,
    maximum_string_utf8_bytes=65_536,
    maximum_total_string_utf8_bytes=MAX_ENGINE_OUTPUT_BYTES,
    maximum_integer_chars=32,
    maximum_float_chars=64,
    allow_floats=False,
)
DECISION_REGISTRY_JSON_LIMITS = JsonLimits(
    maximum_bytes=MAX_DECISION_REGISTRY_BYTES,
    maximum_depth=32,
    maximum_items=100_000,
    maximum_object_members=4_096,
    maximum_array_items=4_096,
    maximum_key_utf8_bytes=128,
    maximum_string_utf8_bytes=65_536,
    maximum_total_string_utf8_bytes=MAX_DECISION_REGISTRY_BYTES,
    maximum_integer_chars=32,
    maximum_float_chars=64,
    allow_floats=False,
)
FENCE_JSON_LIMITS = JsonLimits(
    maximum_bytes=MAX_JSON_FENCE_BYTES,
    maximum_depth=32,
    maximum_items=100_000,
    maximum_object_members=4_096,
    maximum_array_items=4_096,
    maximum_key_utf8_bytes=128,
    maximum_string_utf8_bytes=65_536,
    maximum_total_string_utf8_bytes=MAX_JSON_FENCE_BYTES,
    maximum_integer_chars=32,
    maximum_float_chars=64,
    allow_floats=False,
)


class CoordinatorError(RuntimeError):
    """A bounded source, subprocess, or exact-parity check failed closed."""


@dataclass(frozen=True, slots=True)
class PreparedCorpus:
    value: dict[str, Any]
    sha256: str
    decision_set_binding: dict[str, Any]
    source_identities: list[dict[str, Any]]
    expected_cases: list[dict[str, Any]]
    case_count: int
    mutation_count: int
    engine_timeout_seconds: int
    maximum_engine_output_bytes: int


def _fail(message: str) -> NoReturn:
    raise CoordinatorError(message)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _extract_exact_json_fences(markdown: bytes, *, label: str) -> list[bytes]:
    try:
        markdown.decode("utf-8")
    except UnicodeDecodeError as error:
        _fail(f"{label} is not UTF-8: {error}")

    fences: list[bytes] = []
    state: tuple[str, int] | None = None
    line_start = 0
    while line_start < len(markdown):
        newline = markdown.find(b"\n", line_start)
        line_end = newline if newline >= 0 else len(markdown)
        logical_end = line_end
        if logical_end > line_start and markdown[logical_end - 1] == 0x0D:
            logical_end -= 1
        line = markdown[line_start:logical_end]
        next_line = line_end + 1 if line_end < len(markdown) else len(markdown)

        if state is None and line == b"```json":
            if line_end == len(markdown):
                _fail(f"{label} JSON fence opener has no following content line")
            state = ("json", next_line)
        elif state is None and line.startswith(b"```"):
            state = ("other", 0)
        elif state is not None and state[0] == "json" and line == b"```":
            content_end = line_start
            if content_end > state[1] and markdown[content_end - 1] == 0x0A:
                content_end -= 1
                if content_end > state[1] and markdown[content_end - 1] == 0x0D:
                    content_end -= 1
            fences.append(markdown[state[1] : content_end])
            state = None
        elif state is not None and state[0] == "other" and line == b"```":
            state = None
        line_start = next_line

    if state is not None:
        _fail(f"{label} contains an unclosed Markdown fence")
    return fences


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(f"{label} is not an exact JSON object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        _fail(f"{label} is not an exact JSON array")
    return value


def _string(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        _fail(f"{label} is not a nonempty exact string")
    return value


def _main_adr_path(value: Any, decision_id: str, label: str) -> str:
    path = _string(value, label)
    match = ADR_MAIN_PATH.fullmatch(path)
    path_decision_id = f"ADR-{int(match.group(1)):03d}" if match is not None else None
    if path_decision_id != decision_id:
        _fail(f"{label} is not the matching canonical ADR Markdown path")
    return path


def _module_adr_path(value: Any, decision_id: str, label: str) -> str:
    path = _string(value, label)
    match = ADR_MODULE_PATH.fullmatch(path)
    path_decision_id = f"ADR-{int(match.group(1)):03d}" if match is not None else None
    if path_decision_id != decision_id:
        _fail(f"{label} is not a matching canonical ADR module path")
    return path


def _positive_integer(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        _fail(f"{label} is not a positive exact integer")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        _fail(f"{label} does not have the closed v1 member set")


def _sorted_unique_strings(value: Any, label: str) -> list[str]:
    values = _array(value, label)
    if any(type(item) is not str or not item for item in values):
        _fail(f"{label} contains a non-string or empty identifier")
    if values != sorted(set(values)):
        _fail(f"{label} is not sorted and duplicate-free")
    return values


def _validate_pointer(value: Any, label: str) -> str:
    pointer = _string(value, label)
    if len(pointer.encode("utf-8")) > MAX_PATCH_PATH_BYTES or not pointer.startswith(
        "/"
    ):
        _fail(f"{label} is not a bounded non-root JSON pointer")
    index = 0
    while index < len(pointer):
        if pointer[index] == "~":
            if index + 1 >= len(pointer) or pointer[index + 1] not in "01":
                _fail(f"{label} contains an invalid JSON-pointer escape")
            index += 2
        else:
            index += 1
    return pointer


def _load_json_file(
    relative_path: str,
    *,
    maximum_bytes: int,
    limits: JsonLimits,
    label: str,
) -> tuple[bytes, Any]:
    try:
        raw = read_bounded_relative_file(
            REPOSITORY,
            relative_path,
            maximum_bytes=maximum_bytes,
            label=label,
        )
        return raw, parse_json_bytes(raw, limits=limits, label=label)
    except (BoundedJsonError, OSError, SourceInventoryError) as error:
        raise CoordinatorError(f"{label} failed closed: {error}") from error


def _verify_decision_set_binding(
    binding_value: Any,
) -> dict[str, tuple[str, int, str]]:
    binding = _object(binding_value, "decision_set_binding")
    expected_keys = set(EXPECTED_DECISION_SET_RECIPE) | {
        "projection_byte_length",
        "projection_sha256",
        "sha256",
        "semantic_closure",
    }
    _exact_keys(binding, expected_keys, "decision_set_binding")
    if any(
        binding.get(key) != value for key, value in EXPECTED_DECISION_SET_RECIPE.items()
    ):
        _fail("decision_set_binding does not use the closed v1 recipe")
    projection_byte_length = _positive_integer(
        binding.get("projection_byte_length"), "decision projection byte length"
    )
    if projection_byte_length > MAX_CORPUS_BYTES:
        _fail("decision projection exceeds its byte bound")
    for member in ("projection_sha256", "sha256"):
        if not HEX64.fullmatch(_string(binding.get(member), member)):
            _fail(f"{member} is not lowercase SHA-256")
    closure = _object(binding.get("semantic_closure"), "semantic_closure")
    _exact_keys(
        closure,
        {"source", "json_schema"},
        "semantic_closure",
    )
    for member, expected_path, maximum_bytes in (
        ("source", "docs/adr/decision-closure.source.v1.json", MAX_CORPUS_BYTES),
        (
            "json_schema",
            "docs/adr/decision-closure.source.schema.v1.json",
            MAX_CORPUS_BYTES,
        ),
    ):
        identity = _object(closure.get(member), f"semantic_closure.{member}")
        _exact_keys(identity, {"path", "bytes", "sha256"}, f"semantic_closure.{member}")
        if identity.get("path") != expected_path:
            _fail(f"semantic_closure.{member} has an unexpected path")
        artifact_bytes = _positive_integer(
            identity.get("bytes"), f"semantic_closure.{member}.bytes"
        )
        digest = _string(identity.get("sha256"), f"semantic_closure.{member}.sha256")
        if artifact_bytes > maximum_bytes or not HEX64.fullmatch(digest):
            _fail(f"semantic_closure.{member} identity is invalid")
        try:
            raw = read_bounded_relative_file(
                REPOSITORY,
                expected_path,
                maximum_bytes=maximum_bytes,
                label=f"semantic closure {member}",
            )
        except (OSError, SourceInventoryError) as error:
            raise CoordinatorError(
                f"semantic closure {member} failed closed: {error}"
            ) from error
        if len(raw) != artifact_bytes or _sha256(raw) != digest:
            _fail(f"semantic_closure.{member} bytes differ from the binding")
    _raw, registry_value = _load_json_file(
        binding["registry_path"],
        maximum_bytes=MAX_DECISION_REGISTRY_BYTES,
        limits=DECISION_REGISTRY_JSON_LIMITS,
        label="proposed decision registry",
    )
    registry = _object(registry_value, "proposed decision registry")
    if (
        registry.get("normative") is not False
        or registry.get("promotion_blocked") is not True
    ):
        _fail("decision registry is not explicitly non-normative and promotion-blocked")

    registered_identity = {
        key: binding[key]
        for key in (
            "schema",
            "digest_algorithm",
            "domain_hex",
            "sha256",
            "semantic_closure",
        )
    }
    registry_decision_set = _object(
        registry.get("decision_set"), "decision registry decision_set"
    )
    if registry_decision_set != registered_identity:
        _fail("decision registry has a different decision-set identity")
    _verify_review_packet_binding(registry, registered_identity)

    raw_decisions = _array(registry.get("decisions"), "decision registry decisions")
    projected_decisions: list[dict[str, Any]] = []
    identities: dict[str, tuple[str, int, str]] = {}
    projected_sources: dict[str, tuple[int, str]] = {}
    member_names = binding["decision_members"]
    for index, raw_decision in enumerate(raw_decisions):
        decision = _object(raw_decision, f"decision registry decision {index}")
        missing = [name for name in member_names if name not in decision]
        if missing:
            _fail(f"decision registry decision {index} lacks projection members")
        projection = {name: decision[name] for name in member_names}
        projected_decisions.append(projection)
        decision_id = _string(decision.get("id"), f"decision {index} id")
        path = _main_adr_path(
            decision.get("path"), decision_id, f"decision {decision_id} path"
        )
        byte_length = _positive_integer(
            decision.get("bytes"), f"decision {decision_id} bytes"
        )
        digest = _string(
            decision.get("content_sha256"),
            f"decision {decision_id} content_sha256",
        )
        if (
            decision_id not in EXPECTED_ADR_IDS
            or byte_length > MAX_ADR_BYTES
            or not HEX64.fullmatch(digest)
            or decision_id in identities
        ):
            _fail("decision identities are duplicate or not lowercase SHA-256")
        identities[decision_id] = (path, byte_length, digest)
        source_set = _object(
            decision.get("source_set"), f"decision {decision_id} source_set"
        )
        _exact_keys(
            source_set,
            {
                "schema",
                "decision_id",
                "sources",
                "digest_algorithm",
                "domain_hex",
                "sha256",
            },
            f"decision {decision_id} source_set",
        )
        sources = _array(
            source_set.get("sources"), f"decision {decision_id} source_set sources"
        )
        module_paths = _array(
            decision.get("module_paths"), f"decision {decision_id} module_paths"
        )
        if (
            source_set.get("schema") != ADR_SOURCE_SET_SCHEMA
            or source_set.get("decision_id") != decision_id
            or source_set.get("digest_algorithm") != ADR_SOURCE_SET_DIGEST_ALGORITHM
            or source_set.get("domain_hex") != ADR_SOURCE_SET_DOMAIN_HEX
            or not 1 <= len(sources) <= MAX_ADR_MODULES_PER_DECISION + 1
            or len(module_paths) + 1 != len(sources)
        ):
            _fail(f"decision {decision_id} source_set identity is invalid")
        for source_index, source_value in enumerate(sources):
            source = _object(
                source_value, f"decision {decision_id} source_set source {source_index}"
            )
            _exact_keys(
                source,
                {"kind", "path", "bytes", "sha256"},
                f"decision {decision_id} source_set source {source_index}",
            )
            if source.get("kind") != ("main" if source_index == 0 else "module"):
                _fail(f"decision {decision_id} source_set kind is invalid")
            source_path = _string(source.get("path"), "projected source path")
            source_bytes = _positive_integer(
                source.get("bytes"), "projected source bytes"
            )
            source_digest = _string(source.get("sha256"), "projected source SHA-256")
            if (
                source_bytes > MAX_ADR_BYTES
                or not HEX64.fullmatch(source_digest)
                or source_path in projected_sources
            ):
                _fail(
                    f"decision {decision_id} projected source is invalid or duplicate"
                )
            if source_index == 0:
                if (
                    _main_adr_path(
                        source_path,
                        decision_id,
                        f"decision {decision_id} source_set main path",
                    )
                    != path
                    or source_bytes != byte_length
                    or source_digest != digest
                ):
                    _fail(f"decision {decision_id} source_set main identity differs")
            elif (
                _module_adr_path(
                    source_path,
                    decision_id,
                    f"decision {decision_id} source_set module path",
                )
                != module_paths[source_index - 1]
            ):
                _fail(f"decision {decision_id} source_set module identity differs")
            projected_sources[source_path] = (source_bytes, source_digest)
        source_set_projection = {
            "schema": ADR_SOURCE_SET_SCHEMA,
            "decision_id": decision_id,
            "sources": sources,
        }
        source_set_payload = _canonical_json(source_set_projection)
        source_set_committed = (
            bytes.fromhex(ADR_SOURCE_SET_DOMAIN_HEX)
            + len(source_set_payload).to_bytes(8, "big")
            + source_set_payload
        )
        source_set_digest = _string(
            source_set.get("sha256"), f"decision {decision_id} source_set SHA-256"
        )
        if (
            not HEX64.fullmatch(source_set_digest)
            or _sha256(source_set_committed) != source_set_digest
        ):
            _fail(f"decision {decision_id} source_set commitment does not recompute")

    projection = {
        "schema": binding["schema"],
        "candidate": registry.get("candidate"),
        "wire_version": registry.get("wire_version"),
        "review_policy": registry.get("review_policy"),
        "semantic_closure": registry_decision_set.get("semantic_closure"),
        "decisions": projected_decisions,
    }
    if list(projection) != binding["projection_members"]:
        _fail("decision-set projection member order differs from its closed recipe")
    projection_bytes = _canonical_json(projection)
    if (
        len(projection_bytes) != binding["projection_byte_length"]
        or _sha256(projection_bytes) != binding["projection_sha256"]
    ):
        _fail("decision-set projection bytes differ from the closed binding")
    domain = bytes.fromhex(binding["domain_hex"])
    committed = domain + len(projection_bytes).to_bytes(8, "big") + projection_bytes
    if _sha256(committed) != binding["sha256"]:
        _fail("decision-set domain commitment does not recompute")
    if tuple(sorted(identities)) != EXPECTED_ADR_IDS:
        _fail("decision-set projection does not cover exactly ADR-001 through ADR-011")
    aggregate = 0
    for source_path, (source_bytes, source_digest) in projected_sources.items():
        raw = read_bounded_relative_file(
            REPOSITORY,
            source_path,
            maximum_bytes=source_bytes,
            label=f"projected source {source_path}",
        )
        aggregate += len(raw)
        if (
            aggregate > MAX_AGGREGATE_ADR_BYTES
            or len(raw) != source_bytes
            or _sha256(raw) != source_digest
        ):
            _fail(f"projected source {source_path} differs from its binding")
    return identities


def _verify_review_packet_binding(
    registry: dict[str, Any], registered_identity: dict[str, Any]
) -> None:
    review_records = _array(registry.get("review_records"), "review_records")
    lifecycle = _object(
        registry.get("review_packet_lifecycle"), "review_packet_lifecycle"
    )
    _exact_keys(lifecycle, {"schema", "state"}, "review_packet_lifecycle")
    if lifecycle.get("schema") != REVIEW_PACKET_LIFECYCLE_SCHEMA:
        _fail("review_packet_lifecycle has a different schema")
    state = _string(lifecycle.get("state"), "review_packet_lifecycle state")
    if state == "CURRENT":
        review_subject = _object(
            registry.get("review_packet_subject"), "review_packet_subject"
        )
        _exact_keys(review_subject, {"decision_set"}, "review_packet_subject")
        if review_subject.get("decision_set") != registered_identity:
            _fail("review subject has a different decision-set identity")
        return
    if state in {"SUPERSEDED", "TEMPLATE"}:
        if (
            "review_packet_subject" not in registry
            or registry["review_packet_subject"] is not None
        ):
            _fail("non-current review packet subject is not null")
        if review_records:
            _fail("non-current review packet retains review records")
        return
    _fail("review_packet_lifecycle state is not recognized")


def _validate_expected_diagnostics(
    value: Any,
    *,
    registry: set[str],
    label: str,
) -> list[str]:
    diagnostics = _sorted_unique_strings(value, label)
    if any(not DIAGNOSTIC_ID.fullmatch(item) for item in diagnostics):
        _fail(f"{label} contains an invalid diagnostic identifier")
    if not set(diagnostics).issubset(registry):
        _fail(f"{label} contains an unregistered diagnostic")
    return diagnostics


def _validate_expected_observation(
    result: Any,
    production: Any,
    diagnostics: list[str],
    *,
    label: str,
) -> None:
    if (result == "REJECT") != bool(diagnostics):
        _fail(f"{label} result and diagnostics conflict")
    if result == "REJECT" and production == "NOT_EVALUATED":
        _fail(f"{label} marks a rejected profile as NOT_EVALUATED")


def _validate_mutation(
    value: Any,
    *,
    case_label: str,
    mutation_ids: set[str],
    registry: set[str],
) -> dict[str, Any]:
    mutation = _object(value, f"{case_label} mutation")
    _exact_keys(
        mutation,
        {
            "id",
            "purpose",
            "patch",
            "expected_profile_result",
            "production_admission",
            "expected_diagnostics",
            "payload_interpreted",
        },
        f"{case_label} mutation",
    )
    mutation_id = _string(mutation["id"], f"{case_label} mutation id")
    if (
        not CASE_ID.fullmatch(mutation_id)
        or len(mutation_id.encode("utf-8")) > 160
        or mutation_id in mutation_ids
    ):
        _fail(f"{case_label} has a duplicate or invalid mutation id")
    mutation_ids.add(mutation_id)
    purpose = _string(mutation["purpose"], f"mutation {mutation_id} purpose")
    if not purpose.strip() or len(purpose.encode("utf-8")) > MAX_MUTATION_PURPOSE_BYTES:
        _fail(f"mutation {mutation_id} purpose is blank or exceeds its bound")
    patch = _object(mutation["patch"], f"mutation {mutation_id} patch")
    operation = _string(patch.get("op"), f"mutation {mutation_id} patch op")
    if operation not in EXPECTED_CLOSED_VALUES["patch_operation"]:
        _fail(f"mutation {mutation_id} uses an unregistered patch operation")
    expected_patch_keys = {"target", "op", "path"}
    if operation != "REMOVE":
        expected_patch_keys.add("value")
    _exact_keys(patch, expected_patch_keys, f"mutation {mutation_id} patch")
    if patch["target"] not in EXPECTED_CLOSED_VALUES["patch_target"]:
        _fail(f"mutation {mutation_id} uses an unregistered patch target")
    _validate_pointer(patch["path"], f"mutation {mutation_id} patch path")
    if mutation["expected_profile_result"] != "REJECT":
        _fail(f"mutation {mutation_id} is not an expected fail-closed contrast")
    if (
        mutation["production_admission"]
        not in EXPECTED_CLOSED_VALUES["production_admission"]
    ):
        _fail(f"mutation {mutation_id} has an invalid admission boundary")
    mutation_diagnostics = _validate_expected_diagnostics(
        mutation["expected_diagnostics"],
        registry=registry,
        label=f"mutation {mutation_id} diagnostics",
    )
    _validate_expected_observation(
        mutation["expected_profile_result"],
        mutation["production_admission"],
        mutation_diagnostics,
        label=f"mutation {mutation_id}",
    )
    if type(mutation["payload_interpreted"]) is not bool:
        _fail(f"mutation {mutation_id} payload_interpreted is not Boolean")
    return mutation


def _validate_case_records(
    corpus: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    diagnostics = _sorted_unique_strings(
        corpus["diagnostic_registry"], "diagnostic_registry"
    )
    if any(not DIAGNOSTIC_ID.fullmatch(item) for item in diagnostics):
        _fail("diagnostic_registry contains an invalid identifier")
    registry = set(diagnostics)
    cases = _array(corpus["cases"], "cases")
    if len(cases) != EXPECTED_CASE_COUNT:
        _fail(f"corpus does not contain exactly {EXPECTED_CASE_COUNT} cases")
    case_ids: set[str] = set()
    mutation_ids: set[str] = set()
    used_diagnostics: set[str] = set()
    mutation_count = 0
    coordinates: list[tuple[str, int]] = []
    for index, raw_case in enumerate(cases):
        case = _object(raw_case, f"case {index}")
        _exact_keys(
            case,
            {
                "id",
                "source",
                "scope",
                "profile",
                "polarity",
                "expected_profile_result",
                "production_admission",
                "bounded_fixture",
                "expected_diagnostics",
                "payload_interpreted",
                "mutations",
            },
            f"case {index}",
        )
        case_id = _string(case["id"], f"case {index} id")
        if (
            not CASE_ID.fullmatch(case_id)
            or len(case_id.encode("utf-8")) > 160
            or case_id in case_ids
        ):
            _fail(f"case {index} has a duplicate or invalid id")
        case_ids.add(case_id)
        if case["scope"] not in EXPECTED_CLOSED_VALUES["scope"]:
            _fail(f"case {case_id} has an invalid scope")
        if case["polarity"] not in EXPECTED_CLOSED_VALUES["polarity"]:
            _fail(f"case {case_id} has an invalid polarity")
        profile = _string(case["profile"], f"case {case_id} profile")
        if not PROFILE_ID.fullmatch(profile):
            _fail(f"case {case_id} has an invalid profile id")
        if (
            case["expected_profile_result"]
            not in EXPECTED_CLOSED_VALUES["profile_result"]
        ):
            _fail(f"case {case_id} has an invalid expected result")
        if (
            case["production_admission"]
            not in EXPECTED_CLOSED_VALUES["production_admission"]
        ):
            _fail(f"case {case_id} has an invalid admission boundary")
        if type(case["payload_interpreted"]) is not bool:
            _fail(f"case {case_id} payload_interpreted is not Boolean")
        case_diagnostics = _validate_expected_diagnostics(
            case["expected_diagnostics"],
            registry=registry,
            label=f"case {case_id} diagnostics",
        )
        used_diagnostics.update(case_diagnostics)
        _validate_expected_observation(
            case["expected_profile_result"],
            case["production_admission"],
            case_diagnostics,
            label=f"case {case_id}",
        )
        if (case["polarity"] == "POSITIVE") == (
            case["expected_profile_result"] == "REJECT"
        ):
            _fail(f"case {case_id} polarity disagrees with its base profile result")
        if (case["scope"] == "NON_WIRE_INTERNAL_STATE") != (
            case["expected_profile_result"] == "MATCH_NON_WIRE_EXCERPT"
        ):
            _fail(f"case {case_id} scope disagrees with its base profile result")
        if (
            len(_canonical_json(case["bounded_fixture"]))
            > corpus["limits"]["maximum_fixture_bytes"]
        ):
            _fail(f"case {case_id} fixture exceeds its byte bound")

        source = _object(case["source"], f"case {case_id} source")
        _exact_keys(
            source,
            {
                "adr",
                "json_fence_ordinal",
                "fence_byte_length",
                "fence_sha256",
            },
            f"case {case_id} source",
        )
        adr = _string(source["adr"], f"case {case_id} source ADR")
        if adr not in EXPECTED_ADR_IDS:
            _fail(f"case {case_id} source ADR is unknown")
        case_namespace = adr.lower().replace("-", "") + "."
        profile_namespace = adr.replace("-", "") + "_"
        if not case_id.startswith(case_namespace):
            _fail(f"case {case_id} is not namespaced to source {adr}")
        if not profile.startswith(profile_namespace):
            _fail(f"case {case_id} profile is not namespaced to source {adr}")
        if case["polarity"] == "POSITIVE" and case["payload_interpreted"] is not True:
            _fail(f"positive case {case_id} does not interpret its bounded payload")
        ordinal = _positive_integer(
            source["json_fence_ordinal"], f"case {case_id} source ordinal"
        )
        expected_identity = EXPECTED_CASE_IDENTITIES.get(case_id)
        if (
            expected_identity is None
            or (
                profile,
                case["scope"],
                case["polarity"],
                adr,
                ordinal,
            )
            != expected_identity
        ):
            _fail(f"case {case_id} differs from its closed profile/source identity")
        coordinates.append((adr, ordinal))
        _positive_integer(
            source["fence_byte_length"], f"case {case_id} source fence_byte_length"
        )
        digest = _string(source["fence_sha256"], f"case {case_id} source fence_sha256")
        if not HEX64.fullmatch(digest):
            _fail(f"case {case_id} source fence_sha256 is not lowercase SHA-256")

        mutations = _array(case["mutations"], f"case {case_id} mutations")
        minimum_mutations = EXPECTED_LIMITS["minimum_mutations_per_case"]
        maximum_mutations = EXPECTED_LIMITS["maximum_mutations_per_case"]
        if not minimum_mutations <= len(mutations) <= maximum_mutations:
            _fail(
                f"case {case_id} mutation count is outside "
                f"{minimum_mutations}..{maximum_mutations}"
            )
        for mutation in mutations:
            validated_mutation = _validate_mutation(
                mutation,
                case_label=f"case {case_id}",
                mutation_ids=mutation_ids,
                registry=registry,
            )
            if not validated_mutation["id"].startswith(case_namespace):
                _fail(
                    f"mutation {validated_mutation['id']} is not namespaced to "
                    f"source {adr}"
                )
            used_diagnostics.update(validated_mutation["expected_diagnostics"])
            base_observable = (
                case["expected_profile_result"],
                case["production_admission"],
                tuple(case["expected_diagnostics"]),
                case["payload_interpreted"],
            )
            mutation_observable = (
                validated_mutation["expected_profile_result"],
                validated_mutation["production_admission"],
                tuple(validated_mutation["expected_diagnostics"]),
                validated_mutation["payload_interpreted"],
            )
            if mutation_observable == base_observable:
                mutation_id = validated_mutation["id"]
                _fail(f"mutation {mutation_id} has no observable expected effect")
        mutation_count += len(mutations)
    if coordinates != sorted(coordinates) or len(set(coordinates)) != len(coordinates):
        _fail("case source coordinates are duplicate or not in deterministic order")
    if mutation_count != EXPECTED_LIMITS["expected_mutation_count"]:
        _fail("corpus mutation count differs from its closed declared total")
    if case_ids != set(EXPECTED_CASE_IDENTITIES):
        _fail("corpus case inventory differs from the closed v1 identities")
    if not case_ids.isdisjoint(mutation_ids):
        _fail("case and mutation identifiers must be globally unique")
    if used_diagnostics != registry:
        _fail("diagnostic_registry must exactly cover the v1 corpus expectations")
    diagnostic_payload = _canonical_json(diagnostics)
    if (
        len(diagnostics) != EXPECTED_DIAGNOSTIC_REGISTRY_COUNT
        or len(diagnostic_payload) != EXPECTED_DIAGNOSTIC_REGISTRY_BYTE_LENGTH
        or _sha256(diagnostic_payload) != EXPECTED_DIAGNOSTIC_REGISTRY_SHA256
    ):
        _fail("diagnostic_registry differs from the closed v1 vocabulary")
    return cases, mutation_count


def _verify_source_bindings(
    cases: list[dict[str, Any]],
    decision_identities: dict[str, tuple[str, int, str]],
) -> list[dict[str, Any]]:
    by_path: dict[str, bytes] = {}
    source_identities: list[dict[str, Any]] = []
    covered: set[tuple[str, int]] = set()
    for case in cases:
        source = case["source"]
        adr = source["adr"]
        path, decision_bytes, decision_sha256 = decision_identities[adr]
        if path not in by_path:
            try:
                by_path[path] = read_bounded_relative_file(
                    REPOSITORY,
                    path,
                    maximum_bytes=MAX_ADR_BYTES,
                    label=f"{adr} source",
                )
            except (OSError, SourceInventoryError) as error:
                raise CoordinatorError(f"{adr} source read failed: {error}") from error
        adr_bytes = by_path[path]
        if len(adr_bytes) != decision_bytes or _sha256(adr_bytes) != decision_sha256:
            _fail(f"{adr} bytes do not match the corpus and decision set")
        fences = _extract_exact_json_fences(adr_bytes, label=f"{adr} source")
        ordinal = source["json_fence_ordinal"]
        if ordinal > len(fences):
            _fail(f"case {case['id']} fence ordinal is outside its ADR")
        fence = fences[ordinal - 1]
        if (
            len(fence) != source["fence_byte_length"]
            or _sha256(fence) != source["fence_sha256"]
        ):
            _fail(f"case {case['id']} fence bytes differ from the corpus")
        try:
            parse_json_bytes(
                fence,
                limits=FENCE_JSON_LIMITS,
                label=f"case {case['id']} fence",
            )
        except BoundedJsonError as error:
            raise CoordinatorError(
                f"case {case['id']} fence JSON failed closed: {error}"
            ) from error
        coordinate = (path, ordinal)
        if coordinate in covered:
            _fail(f"case {case['id']} duplicates a fence binding")
        covered.add(coordinate)
        source_identities.append(
            {
                "case_id": case["id"],
                "path": path,
                "json_fence_ordinal": ordinal,
                "adr_byte_length": decision_bytes,
                "adr_sha256": decision_sha256,
                "fence_byte_length": source["fence_byte_length"],
                "fence_sha256": source["fence_sha256"],
            }
        )
    if tuple(sorted({case["source"]["adr"] for case in cases})) != EXPECTED_ADR_IDS:
        _fail("case source bindings do not cover exactly ADR-001 through ADR-011")
    for path, adr_bytes in by_path.items():
        fence_count = len(_extract_exact_json_fences(adr_bytes, label=f"{path} source"))
        expected = {(path, ordinal) for ordinal in range(1, fence_count + 1)}
        actual = {coordinate for coordinate in covered if coordinate[0] == path}
        if actual != expected:
            _fail(f"ADR source {path} JSON fence coverage is not exact and contiguous")
    if sum(len(value) for value in by_path.values()) > MAX_AGGREGATE_ADR_BYTES:
        _fail("ADR source corpus exceeds its aggregate byte bound")
    for path, original in by_path.items():
        try:
            current = read_bounded_relative_file(
                REPOSITORY,
                path,
                maximum_bytes=MAX_ADR_BYTES,
                label=f"final source snapshot {path}",
            )
        except (OSError, SourceInventoryError) as error:
            raise CoordinatorError(f"final source snapshot failed: {error}") from error
        if current != original:
            _fail(f"ADR source {path} changed during corpus preparation")
    return source_identities


def _expected_case_results(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": case["id"],
            "profile_result": case["expected_profile_result"],
            "production_admission": case["production_admission"],
            "diagnostics": case["expected_diagnostics"],
            "payload_interpreted": case["payload_interpreted"],
            "mutations": [
                {
                    "id": mutation["id"],
                    "profile_result": mutation["expected_profile_result"],
                    "production_admission": mutation["production_admission"],
                    "diagnostics": mutation["expected_diagnostics"],
                    "payload_interpreted": mutation["payload_interpreted"],
                }
                for mutation in case["mutations"]
            ],
        }
        for case in cases
    ]


def _prepare_corpus_value(raw: bytes, value: Any) -> PreparedCorpus:
    corpus = _object(value, "ADR semantic corpus")
    _exact_keys(
        corpus,
        {
            "schema",
            "schema_version",
            "task",
            "candidate",
            "wire_version",
            "decision_set_binding",
            "source_binding",
            "limits",
            "closed_values",
            "diagnostic_registry",
            "claim_boundary",
            "cases",
        },
        "ADR semantic corpus",
    )
    if (
        corpus["schema"] != CORPUS_SCHEMA
        or corpus["schema_version"] != 1
        or corpus["task"] != "B01"
        or corpus["candidate"] != "1.0.0-rc.1"
        or corpus["wire_version"] != "1.0"
    ):
        _fail("ADR semantic corpus identity fields differ from v1")
    if corpus["source_binding"] != EXPECTED_SOURCE_BINDING:
        _fail("ADR semantic corpus source binding differs from v1")
    if corpus["limits"] != EXPECTED_LIMITS:
        _fail("ADR semantic corpus limits differ from the closed v1 limits")
    if corpus["closed_values"] != EXPECTED_CLOSED_VALUES:
        _fail("ADR semantic corpus closed values differ from v1")
    claims = _object(corpus["claim_boundary"], "claim_boundary")
    _exact_keys(claims, EXPECTED_CLAIM_BOUNDARY_KEYS, "claim_boundary")
    if any(value is not False for value in claims.values()):
        _fail("claim_boundary must be the exact false-only v1 member set")
    decision_identities = _verify_decision_set_binding(corpus["decision_set_binding"])
    cases, mutation_count = _validate_case_records(corpus)
    sources = _verify_source_bindings(cases, decision_identities)
    return PreparedCorpus(
        value=corpus,
        sha256=_sha256(raw),
        decision_set_binding=deepcopy(corpus["decision_set_binding"]),
        source_identities=sources,
        expected_cases=_expected_case_results(cases),
        case_count=len(cases),
        mutation_count=mutation_count,
        engine_timeout_seconds=corpus["limits"]["engine_timeout_seconds"],
        maximum_engine_output_bytes=corpus["limits"]["maximum_engine_output_bytes"],
    )


def prepare_corpus() -> PreparedCorpus:
    raw, value = _load_json_file(
        CORPUS_RELATIVE_PATH,
        maximum_bytes=MAX_CORPUS_BYTES,
        limits=CORPUS_JSON_LIMITS,
        label="ADR semantic corpus",
    )
    prepared = _prepare_corpus_value(raw, value)
    try:
        final_raw = read_bounded_relative_file(
            REPOSITORY,
            CORPUS_RELATIVE_PATH,
            maximum_bytes=MAX_CORPUS_BYTES,
            label="final ADR semantic corpus snapshot",
        )
    except (OSError, SourceInventoryError) as error:
        raise CoordinatorError(f"final corpus snapshot failed: {error}") from error
    if final_raw != raw:
        _fail("ADR semantic corpus changed while it was prepared")
    return prepared


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=1)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass


def _bounded_process(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    stdout_limit: int,
    label: str,
    environment_overrides: dict[str, str] | None = None,
) -> bytes:
    environment = os.environ.copy()
    environment.pop("CARGO_TARGET_DIR", None)
    environment.update(
        {
            "CARGO_TERM_COLOR": "never",
            "LC_ALL": "C",
            "LANG": "C",
            "NO_COLOR": "1",
            "TZ": "UTC",
        }
    )
    if environment_overrides is not None:
        environment.update(environment_overrides)
    try:
        process = subprocess.Popen(  # noqa: S603
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            start_new_session=True,
        )
    except OSError as error:
        raise CoordinatorError(f"cannot start {label}: {error}") from error
    if process.stdout is None or process.stderr is None:
        _terminate_process(process)
        _fail(f"{label} did not expose bounded output pipes")

    selector = selectors.DefaultSelector()
    streams = {
        process.stdout: ("stdout", stdout_limit),
        process.stderr: ("stderr", MAX_ENGINE_STDERR_BYTES),
    }
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    for stream in streams:
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout_seconds
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _terminate_process(process)
                _fail(f"{label} exceeded its {timeout_seconds}-second timeout")
            events = selector.select(min(remaining, 0.25))
            for key, _mask in events:
                stream = key.fileobj
                name, limit = streams[stream]
                try:
                    chunk = os.read(stream.fileno(), 8_192)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(stream)
                    continue
                if len(buffers[name]) + len(chunk) > limit:
                    _terminate_process(process)
                    _fail(f"{label} {name} exceeds its {limit}-byte bound")
                buffers[name].extend(chunk)
        remaining = max(0.0, deadline - time.monotonic())
        try:
            return_code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            _terminate_process(process)
            _fail(f"{label} did not terminate within its timeout")
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()
    stderr = bytes(buffers["stderr"])
    stdout = bytes(buffers["stdout"])
    if return_code != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()[-2_000:]
        _fail(f"{label} exited {return_code}: {detail}")
    if stderr:
        _fail(f"{label} emitted stderr on a successful run")
    if not stdout:
        _fail(f"{label} emitted no result")
    return stdout


def _engine_command(engine: str, *, self_test: bool) -> tuple[list[str], Path]:
    suffix = ["--self-test"] if self_test else []
    if engine == "rust":
        cargo = shutil.which("cargo")
        if cargo is None:
            _fail("cargo is unavailable for the separate Rust engine")
        if not RUST_MANIFEST.is_file():
            _fail("the separate Rust engine manifest is missing")
        return (
            [
                cargo,
                "run",
                "--quiet",
                "--offline",
                "--locked",
                "--manifest-path",
                str(RUST_MANIFEST),
                "--",
                "--corpus",
                str(CORPUS_PATH),
                "--repo-root",
                str(REPOSITORY),
                *suffix,
            ],
            REPOSITORY,
        )
    if engine == "typescript":
        bun = shutil.which("bun")
        if bun is None:
            _fail("bun is unavailable for the separate TypeScript engine")
        if not TYPESCRIPT_MAIN.is_file():
            _fail("the separate TypeScript engine entry point is missing")
        return (
            [
                bun,
                "run",
                str(TYPESCRIPT_MAIN),
                "--corpus",
                str(CORPUS_PATH),
                "--repo-root",
                str(REPOSITORY),
                *suffix,
            ],
            TYPESCRIPT_ROOT,
        )
    _fail(f"unknown engine {engine!r}")


def _expected_engine_projection(prepared: PreparedCorpus) -> dict[str, Any]:
    return {
        "schema": ENGINE_RESULT_SCHEMA,
        "schema_version": 1,
        "semantic_claim": SEMANTIC_CLAIM,
        "decision_set_binding": prepared.decision_set_binding,
        "corpus_sha256": prepared.sha256,
        "case_count": prepared.case_count,
        "mutation_count": prepared.mutation_count,
        "source_identities": prepared.source_identities,
        "cases": prepared.expected_cases,
    }


def _engine_source_identities(engine: str) -> list[dict[str, Any]]:
    if engine == "rust":
        engine_root = HARNESS_ROOT / "rust"
        paths = [engine_root / "Cargo.lock", engine_root / "Cargo.toml"]
        paths.extend(sorted((engine_root / "src").glob("*.rs")))
    elif engine == "typescript":
        engine_root = HARNESS_ROOT / "typescript"
        paths = [engine_root / "package.json", engine_root / "tsconfig.json"]
        paths.extend(sorted((engine_root / "src").glob("*.ts")))
    else:
        _fail(f"unknown engine source identity request {engine!r}")
    paths = sorted(paths)
    relative_paths = [path.relative_to(REPOSITORY).as_posix() for path in paths]
    if (
        len(relative_paths) < 3
        or relative_paths != sorted(set(relative_paths))
        or any(path.is_symlink() or not path.is_file() for path in paths)
    ):
        _fail(
            f"{engine} engine source set is missing, duplicate, unordered, "
            "or non-regular"
        )
    identities: list[dict[str, Any]] = []
    total_bytes = 0
    for relative_path in relative_paths:
        try:
            content = read_bounded_relative_file(
                REPOSITORY,
                relative_path,
                maximum_bytes=MAX_ENGINE_SOURCE_BYTES,
                label=f"{engine} engine source {relative_path}",
            )
        except (OSError, SourceInventoryError) as error:
            raise CoordinatorError(
                f"{engine} engine source read failed: {error}"
            ) from error
        total_bytes += len(content)
        if total_bytes > MAX_AGGREGATE_ENGINE_SOURCE_BYTES:
            _fail(f"{engine} engine source set exceeds its aggregate byte bound")
        identities.append(
            {
                "path": relative_path,
                "byte_length": len(content),
                "sha256": _sha256(content),
            }
        )
    return identities


def _parse_engine_output(
    raw: bytes,
    *,
    engine: str,
    prepared: PreparedCorpus,
    require_self_tests: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        value = parse_json_bytes(
            raw,
            limits=ENGINE_OUTPUT_JSON_LIMITS,
            label=f"{engine} semantic-engine output",
        )
    except BoundedJsonError as error:
        raise CoordinatorError(
            f"{engine} output failed bounded JSON: {error}"
        ) from error
    result = _object(value, f"{engine} semantic-engine output")
    expected_keys = set(_expected_engine_projection(prepared)) | {"engine"}
    expected_keys.add("engine_source_identities")
    if "self_tests" in result:
        expected_keys.add("self_tests")
    _exact_keys(result, expected_keys, f"{engine} semantic-engine output")
    if result["engine"] != engine:
        _fail(f"{engine} semantic engine returned a different engine identity")
    engine_sources = _array(
        result["engine_source_identities"], f"{engine} engine_source_identities"
    )
    if engine_sources != _engine_source_identities(engine):
        _fail(f"{engine} semantic engine source identities differ from exact bytes")
    self_tests = result.get("self_tests")
    if require_self_tests and self_tests is None:
        _fail(f"{engine} semantic engine omitted required self-tests")
    if self_tests is not None:
        tests = _object(self_tests, f"{engine} self_tests")
        _exact_keys(tests, {"executed", "detected"}, f"{engine} self_tests")
        executed = _positive_integer(tests["executed"], f"{engine} self-tests executed")
        detected = _positive_integer(tests["detected"], f"{engine} self-tests detected")
        expected_count = EXPECTED_ENGINE_SELF_TEST_COUNTS[engine]
        if executed != expected_count or detected != expected_count:
            _fail(
                f"{engine} semantic engine self-test attestation differs "
                "from its closed suite"
            )
    projection = {key: result[key] for key in _expected_engine_projection(prepared)}
    if projection != _expected_engine_projection(prepared):
        _fail(f"{engine} semantic result differs from the source-bound corpus")
    return projection, engine_sources


def _run_engine(
    engine: str,
    *,
    prepared: PreparedCorpus,
    self_test: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    command, cwd = _engine_command(engine, self_test=self_test)
    if engine == "rust":
        _require_source_tree_build_output_absent(HARNESS_ROOT)
        with tempfile.TemporaryDirectory(prefix="ncp-b01-adr-semantics-") as target:
            raw = _bounded_process(
                command,
                cwd=cwd,
                timeout_seconds=prepared.engine_timeout_seconds,
                stdout_limit=prepared.maximum_engine_output_bytes,
                label=f"separate {engine} ADR semantic engine",
                environment_overrides={"CARGO_TARGET_DIR": target},
            )
        _require_source_tree_build_output_absent(HARNESS_ROOT)
    else:
        raw = _bounded_process(
            command,
            cwd=cwd,
            timeout_seconds=prepared.engine_timeout_seconds,
            stdout_limit=prepared.maximum_engine_output_bytes,
            label=f"separate {engine} ADR semantic engine",
        )
    return _parse_engine_output(
        raw,
        engine=engine,
        prepared=prepared,
        require_self_tests=self_test,
    )


def _require_source_tree_build_output_absent(harness_root: Path) -> None:
    outputs = (
        harness_root / "rust" / "target",
        harness_root / "typescript" / "dist",
        harness_root / "typescript" / "node_modules",
    )
    present = [path.name for path in outputs if path.exists()]
    if present:
        _fail(f"semantic-engine source tree contains build output: {present!r}")


def _expect_failure(
    operation: Callable[[], Any],
    label: str,
    expected_exception: type[Exception],
    expected_message: str | None = None,
) -> None:
    try:
        operation()
    except expected_exception as error:
        if expected_message is not None and str(error) != expected_message:
            raise CoordinatorError(
                f"coordinator self-test {label} raised the wrong error"
            ) from error
        return
    except Exception as error:
        raise CoordinatorError(
            f"coordinator self-test {label} raised the wrong exception type"
        ) from error
    raise CoordinatorError(f"coordinator self-test did not detect {label}")


def _coordinator_self_test(prepared: PreparedCorpus) -> dict[str, int]:
    executed = 0

    executed += 1
    nested_fence_markdown = (
        b'```text\n```json\n{"ignored":true}\n```\n'
        b'```json\r\n{"accepted":true}\r\n```\r\n'
    )
    if _extract_exact_json_fences(
        nested_fence_markdown, label="coordinator fence self-test"
    ) != [b'{"accepted":true}']:
        _fail("coordinator exact fence scanner accepted a nested marker")
    if (
        _main_adr_path(
            "docs/adr/0001-canonical-main.md",
            "ADR-001",
            "coordinator ADR-path self-test",
        )
        != "docs/adr/0001-canonical-main.md"
    ):
        _fail("coordinator ADR-path self-test changed a canonical path")
    for hostile_path, hostile_id in (
        ("docs/adr/0001-nested/subject.md", "ADR-001"),
        ("docs/adr/0001-wrong-decision.md", "ADR-002"),
        ("docs/adr/0001-double--hyphen.md", "ADR-001"),
    ):
        _expect_failure(
            lambda path=hostile_path, decision_id=hostile_id: _main_adr_path(
                path, decision_id, "coordinator ADR-path self-test"
            ),
            f"noncanonical ADR path {hostile_path!r}",
            CoordinatorError,
            (
                "coordinator ADR-path self-test is not the matching canonical "
                "ADR Markdown path"
            ),
        )
    for hostile_path, hostile_id in (
        ("docs/adr/modules/adr-004-nested/subject.md", "ADR-004"),
        ("docs/adr/modules/adr-004-wrong-decision.md", "ADR-009"),
        ("docs/adr/modules/adr-004-double--hyphen.md", "ADR-004"),
    ):
        _expect_failure(
            lambda path=hostile_path, decision_id=hostile_id: _module_adr_path(
                path, decision_id, "coordinator ADR-module self-test"
            ),
            f"noncanonical ADR module path {hostile_path!r}",
            CoordinatorError,
            (
                "coordinator ADR-module self-test is not a matching canonical "
                "ADR module path"
            ),
        )
    executed += 1
    _expect_failure(
        lambda: _extract_exact_json_fences(
            b"```json\n{}\n", label="coordinator unclosed fence self-test"
        ),
        "unclosed exact JSON fence",
        CoordinatorError,
        "coordinator unclosed fence self-test contains an unclosed Markdown fence",
    )

    decision_set_identity = {
        "digest_algorithm": "sha256(domain || u64be(projection_bytes) || projection)",
        "domain_hex": "00",
        "schema": "ncp.b01-decision-set.v1",
        "sha256": "a" * 64,
    }
    mismatched_decision_set_identity = {
        **decision_set_identity,
        "sha256": "b" * 64,
    }
    executed += 1
    _verify_review_packet_binding(
        {
            "review_packet_lifecycle": {
                "schema": REVIEW_PACKET_LIFECYCLE_SCHEMA,
                "state": "CURRENT",
            },
            "review_packet_subject": {"decision_set": decision_set_identity},
            "review_records": [{}],
        },
        decision_set_identity,
    )
    executed += 1
    _verify_review_packet_binding(
        {
            "review_packet_lifecycle": {
                "schema": REVIEW_PACKET_LIFECYCLE_SCHEMA,
                "state": "SUPERSEDED",
            },
            "review_packet_subject": None,
            "review_records": [],
        },
        decision_set_identity,
    )
    executed += 1
    _verify_review_packet_binding(
        {
            "review_packet_lifecycle": {
                "schema": REVIEW_PACKET_LIFECYCLE_SCHEMA,
                "state": "TEMPLATE",
            },
            "review_packet_subject": None,
            "review_records": [],
        },
        decision_set_identity,
    )
    executed += 1
    _expect_failure(
        lambda: _verify_review_packet_binding(
            {
                "review_packet_lifecycle": {
                    "schema": REVIEW_PACKET_LIFECYCLE_SCHEMA,
                    "state": "CURRENT",
                },
                "review_packet_subject": None,
                "review_records": [],
            },
            decision_set_identity,
        ),
        "CURRENT packet without a subject",
        CoordinatorError,
        "review_packet_subject is not an exact JSON object",
    )
    executed += 1
    _expect_failure(
        lambda: _verify_review_packet_binding(
            {
                "review_packet_lifecycle": {
                    "schema": REVIEW_PACKET_LIFECYCLE_SCHEMA,
                    "state": "CURRENT",
                },
                "review_packet_subject": {
                    "decision_set": mismatched_decision_set_identity
                },
                "review_records": [],
            },
            decision_set_identity,
        ),
        "CURRENT packet with a mismatched subject",
        CoordinatorError,
        "review subject has a different decision-set identity",
    )
    executed += 1
    _expect_failure(
        lambda: _verify_review_packet_binding(
            {
                "review_packet_lifecycle": {
                    "schema": REVIEW_PACKET_LIFECYCLE_SCHEMA,
                    "state": "SUPERSEDED",
                },
                "review_packet_subject": {"decision_set": decision_set_identity},
                "review_records": [],
            },
            decision_set_identity,
        ),
        "superseded packet with a review subject",
        CoordinatorError,
        "non-current review packet subject is not null",
    )
    executed += 1
    _expect_failure(
        lambda: _verify_review_packet_binding(
            {
                "review_packet_lifecycle": {
                    "schema": REVIEW_PACKET_LIFECYCLE_SCHEMA,
                    "state": "TEMPLATE",
                },
                "review_packet_subject": {"decision_set": decision_set_identity},
                "review_records": [],
            },
            decision_set_identity,
        ),
        "template packet with a review subject",
        CoordinatorError,
        "non-current review packet subject is not null",
    )
    executed += 1
    _expect_failure(
        lambda: _verify_review_packet_binding(
            {
                "review_packet_lifecycle": {
                    "schema": REVIEW_PACKET_LIFECYCLE_SCHEMA,
                    "state": "SUPERSEDED",
                },
                "review_packet_subject": None,
                "review_records": [{}],
            },
            decision_set_identity,
        ),
        "non-current packet with a review record",
        CoordinatorError,
        "non-current review packet retains review records",
    )
    executed += 1
    _expect_failure(
        lambda: _verify_review_packet_binding(
            {
                "review_packet_lifecycle": {
                    "schema": REVIEW_PACKET_LIFECYCLE_SCHEMA,
                    "state": "UNKNOWN",
                },
                "review_packet_subject": None,
                "review_records": [],
            },
            decision_set_identity,
        ),
        "unknown packet lifecycle",
        CoordinatorError,
        "review_packet_lifecycle state is not recognized",
    )
    executed += 1
    _expect_failure(
        lambda: _verify_review_packet_binding(
            {
                "review_packet_lifecycle": {
                    "schema": "ncp.b01-review-packet-lifecycle.v0",
                    "state": "SUPERSEDED",
                },
                "review_packet_subject": None,
                "review_records": [],
            },
            decision_set_identity,
        ),
        "packet lifecycle with a wrong schema",
        CoordinatorError,
        "review_packet_lifecycle has a different schema",
    )
    executed += 1
    _expect_failure(
        lambda: _verify_review_packet_binding(
            {
                "review_packet_lifecycle": {
                    "schema": REVIEW_PACKET_LIFECYCLE_SCHEMA,
                    "state": "SUPERSEDED",
                    "unexpected": False,
                },
                "review_packet_subject": None,
                "review_records": [],
            },
            decision_set_identity,
        ),
        "packet lifecycle with an extra member",
        CoordinatorError,
        "review_packet_lifecycle does not have the closed v1 member set",
    )
    _expect_failure(
        lambda: _verify_review_packet_binding(
            {
                "review_packet_lifecycle": {
                    "schema": REVIEW_PACKET_LIFECYCLE_SCHEMA,
                    "state": "CURRENT",
                },
                "review_packet_subject": {
                    "decision_set": decision_set_identity,
                    "unexpected": False,
                },
                "review_records": [],
            },
            decision_set_identity,
        ),
        "CURRENT packet subject with an extra member",
        CoordinatorError,
        "review_packet_subject does not have the closed v1 member set",
    )
    executed += 1
    _expect_failure(
        lambda: _verify_review_packet_binding(
            {
                "review_packet_lifecycle": {
                    "schema": REVIEW_PACKET_LIFECYCLE_SCHEMA,
                },
                "review_packet_subject": None,
                "review_records": [],
            },
            decision_set_identity,
        ),
        "packet lifecycle without a state",
        CoordinatorError,
        "review_packet_lifecycle does not have the closed v1 member set",
    )
    executed += 1
    _expect_failure(
        lambda: _verify_review_packet_binding(
            {
                "review_packet_lifecycle": {
                    "schema": REVIEW_PACKET_LIFECYCLE_SCHEMA,
                    "state": "SUPERSEDED",
                },
                "review_records": [],
            },
            decision_set_identity,
        ),
        "non-current packet without a subject member",
        CoordinatorError,
        "non-current review packet subject is not null",
    )
    executed += 1
    _expect_failure(
        lambda: _verify_review_packet_binding(
            {
                "review_packet_lifecycle": {
                    "schema": REVIEW_PACKET_LIFECYCLE_SCHEMA,
                    "state": "CURRENT",
                },
                "review_packet_subject": {"decision_set": decision_set_identity},
            },
            decision_set_identity,
        ),
        "packet without review_records",
        CoordinatorError,
        "review_records is not an exact JSON array",
    )

    executed += 1
    _expect_failure(
        lambda: parse_json_bytes(
            b'{"duplicate":1,"duplicate":2}',
            limits=ENGINE_OUTPUT_JSON_LIMITS,
            label="duplicate-output self-test",
        ),
        "duplicate JSON members",
        BoundedJsonError,
    )

    executed += 1
    altered_binding = deepcopy(prepared.value)
    altered_binding["decision_set_binding"]["semantic_closure"]["source"]["sha256"] = (
        "0" * 64
    )
    _expect_failure(
        lambda: _prepare_corpus_value(b"{}", altered_binding),
        "altered semantic-closure decision-set binding",
        CoordinatorError,
    )

    executed += 1
    altered_fence = deepcopy(prepared.value)
    altered_fence["cases"][0]["source"]["fence_sha256"] = "0" * 64
    _expect_failure(
        lambda: _prepare_corpus_value(b"{}", altered_fence),
        "altered fence binding",
        CoordinatorError,
    )
    altered_case_identity = deepcopy(prepared.value)
    altered_case_identity["cases"][0]["profile"] = "ADR001_ALTERED_V1"
    _expect_failure(
        lambda: _prepare_corpus_value(b"{}", altered_case_identity),
        "altered closed case identity",
        CoordinatorError,
        "case adr001.open-plant-session.kind-separation.v1 differs from its "
        "closed profile/source identity",
    )
    shuffled_case_order = deepcopy(prepared.value)
    shuffled_case_order["cases"][0], shuffled_case_order["cases"][1] = (
        shuffled_case_order["cases"][1],
        shuffled_case_order["cases"][0],
    )
    _expect_failure(
        lambda: _prepare_corpus_value(b"{}", shuffled_case_order),
        "shuffled case source order",
        CoordinatorError,
        "case source coordinates are duplicate or not in deterministic order",
    )

    executed += 1
    unexpected = _expected_engine_projection(prepared)
    unexpected.update(
        {
            "engine": "typescript",
            "engine_source_identities": _engine_source_identities("typescript"),
            "unexpected": False,
        }
    )
    _expect_failure(
        lambda: _parse_engine_output(
            _canonical_json(unexpected),
            engine="typescript",
            prepared=prepared,
            require_self_tests=False,
        ),
        "unknown engine-output member",
        CoordinatorError,
    )

    executed += 1
    divergent = _expected_engine_projection(prepared)
    divergent["engine"] = "typescript"
    divergent["engine_source_identities"] = _engine_source_identities("typescript")
    divergent["cases"] = deepcopy(divergent["cases"])
    divergent["cases"][0]["id"] = "altered.v1"
    _expect_failure(
        lambda: _parse_engine_output(
            _canonical_json(divergent),
            engine="typescript",
            prepared=prepared,
            require_self_tests=False,
        ),
        "semantic result divergence",
        CoordinatorError,
    )

    executed += 1
    with tempfile.TemporaryDirectory(prefix="ncp-b01-build-output-control-") as root:
        hostile_root = Path(root)
        (hostile_root / "rust" / "target").mkdir(parents=True)
        _expect_failure(
            lambda: _require_source_tree_build_output_absent(hostile_root),
            "source-tree build output",
            CoordinatorError,
        )

    executed += 1
    forged_self_tests = _expected_engine_projection(prepared)
    forged_self_tests.update(
        {
            "engine": "typescript",
            "engine_source_identities": _engine_source_identities("typescript"),
            "self_tests": {"executed": 1, "detected": 1},
        }
    )
    _expect_failure(
        lambda: _parse_engine_output(
            _canonical_json(forged_self_tests),
            engine="typescript",
            prepared=prepared,
            require_self_tests=True,
        ),
        "forged one-of-one engine self-test attestation",
        CoordinatorError,
    )

    executed += 1
    wrong_count = deepcopy(prepared.value)
    wrong_count["cases"][0]["mutations"].pop()
    _expect_failure(
        lambda: _prepare_corpus_value(b"{}", wrong_count),
        "off-by-one mutation total",
        CoordinatorError,
        "corpus mutation count differs from its closed declared total",
    )

    executed += 1
    vacuous = deepcopy(prepared.value)
    first_case = vacuous["cases"][1]
    first_mutation = first_case["mutations"][0]
    for key in (
        "expected_profile_result",
        "production_admission",
        "expected_diagnostics",
        "payload_interpreted",
    ):
        first_mutation[key] = deepcopy(first_case[key])
    _expect_failure(
        lambda: _prepare_corpus_value(b"{}", vacuous),
        "observationally vacuous mutation",
        CoordinatorError,
        f"mutation {first_mutation['id']} has no observable expected effect",
    )

    executed += 1
    colliding_identifier = deepcopy(prepared.value)
    colliding_identifier["cases"][0]["mutations"][0]["id"] = colliding_identifier[
        "cases"
    ][0]["id"]
    _expect_failure(
        lambda: _prepare_corpus_value(b"{}", colliding_identifier),
        "case and mutation identifier collision",
        CoordinatorError,
        "case and mutation identifiers must be globally unique",
    )

    executed += 1
    unused_diagnostic = deepcopy(prepared.value)
    unused_diagnostic["diagnostic_registry"].append("ZZZ_UNUSED")
    _expect_failure(
        lambda: _prepare_corpus_value(b"{}", unused_diagnostic),
        "unused diagnostic registry member",
        CoordinatorError,
        "diagnostic_registry must exactly cover the v1 corpus expectations",
    )

    executed += 1
    substituted_diagnostic = deepcopy(prepared.value)
    original_diagnostic = substituted_diagnostic["diagnostic_registry"][0]
    substituted_diagnostic["diagnostic_registry"][0] = "ZZZ_SUBSTITUTED"
    for case in substituted_diagnostic["cases"]:
        case["expected_diagnostics"] = sorted(
            "ZZZ_SUBSTITUTED" if item == original_diagnostic else item
            for item in case["expected_diagnostics"]
        )
        for mutation in case["mutations"]:
            mutation["expected_diagnostics"] = sorted(
                "ZZZ_SUBSTITUTED" if item == original_diagnostic else item
                for item in mutation["expected_diagnostics"]
            )
    substituted_diagnostic["diagnostic_registry"].sort()
    _expect_failure(
        lambda: _prepare_corpus_value(b"{}", substituted_diagnostic),
        "consistently substituted diagnostic vocabulary",
        CoordinatorError,
        "diagnostic_registry differs from the closed v1 vocabulary",
    )

    executed += 1
    try:
        _expect_failure(
            lambda: {}["missing"],
            "unrelated exception",
            CoordinatorError,
        )
    except CoordinatorError as error:
        if "wrong exception type" not in str(error):
            raise
    else:
        _fail("coordinator self-test accepted an unrelated exception type")
    return {"executed": executed, "detected": executed}


def build_result(*, self_test: bool = False) -> dict[str, Any]:
    prepared = prepare_corpus()
    coordinator_tests = (
        _coordinator_self_test(prepared)
        if self_test
        else {"executed": 0, "detected": 0}
    )
    rust, rust_sources = _run_engine("rust", prepared=prepared, self_test=self_test)
    typescript, typescript_sources = _run_engine(
        "typescript", prepared=prepared, self_test=self_test
    )
    if rust != typescript:
        _fail("separate Rust and TypeScript semantic results differ")
    if rust_sources != _engine_source_identities(
        "rust"
    ) or typescript_sources != _engine_source_identities("typescript"):
        _fail("an engine source changed after its result was validated")
    _require_source_tree_build_output_absent(HARNESS_ROOT)
    return {
        "schema": COORDINATOR_RESULT_SCHEMA,
        "task": "B01",
        "candidate": "1.0.0-rc.1",
        "wire_version": "1.0",
        "decision_set_binding": prepared.decision_set_binding,
        "corpus_sha256": prepared.sha256,
        "case_count": prepared.case_count,
        "mutation_count": prepared.mutation_count,
        "engines": ["rust", "typescript"],
        "engine_source_identities": {
            "rust": rust_sources,
            "typescript": typescript_sources,
        },
        "semantic_parity_sha256": _sha256(_canonical_json(rust)),
        "exact_semantic_match": True,
        "exact_source_identity_match": True,
        "source_tree_build_output_absent": True,
        "coordinator_self_tests": coordinator_tests,
        "claim_boundary": deepcopy(prepared.value["claim_boundary"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="also run coordinator and engine-local negative controls",
    )
    arguments = parser.parse_args()
    try:
        result = build_result(self_test=arguments.self_test)
    except (CoordinatorError, MemoryError, OSError, UnicodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        "NCP_B01_ADR_EXAMPLE_SEMANTICS_RESULT="
        + json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
