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
SEMANTIC_CLAIM = "local-prototype-only"
MAX_CORPUS_BYTES = 262_144
MAX_ENGINE_OUTPUT_BYTES = 262_144
MAX_ENGINE_STDERR_BYTES = 65_536
MAX_DECISION_REGISTRY_BYTES = 131_072
MAX_ADR_BYTES = 262_144
MAX_AGGREGATE_ADR_BYTES = 2_097_152
MAX_JSON_FENCE_BYTES = 131_072
MAX_FIXTURE_BYTES = 16_384
MAX_ENGINE_SOURCE_BYTES = 262_144
MAX_AGGREGATE_ENGINE_SOURCE_BYTES = 2_097_152
EXPECTED_CASE_COUNT = 22
EXPECTED_ENGINE_SELF_TEST_COUNTS = {"rust": 10, "typescript": 25}
EXPECTED_ADR_IDS = tuple(f"ADR-{index:03d}" for index in range(1, 12))
JSON_FENCE = re.compile(rb"```json\n(.*?)\n```", re.DOTALL)
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
CASE_ID = re.compile(r"[a-z0-9][a-z0-9.-]*\.v1\Z")
PROFILE_ID = re.compile(r"ADR(?:00[1-9]|01[01])_[A-Z0-9_]+_V1\Z")
DIAGNOSTIC_ID = re.compile(r"[A-Z][A-Z0-9_]*\Z")
ADR_PATH = re.compile(r"docs/adr/(00(?:0[1-9]|1[01]))-[a-z0-9-]+\.md\Z")

EXPECTED_LIMITS = {
    "maximum_corpus_bytes": MAX_CORPUS_BYTES,
    "maximum_aggregate_adr_bytes": MAX_AGGREGATE_ADR_BYTES,
    "maximum_adr_bytes": MAX_ADR_BYTES,
    "maximum_json_fence_bytes": MAX_JSON_FENCE_BYTES,
    "maximum_json_depth": 32,
    "maximum_json_nodes": 100_000,
    "maximum_object_members": 4_096,
    "maximum_array_items": 4_096,
    "maximum_key_utf8_bytes": 256,
    "maximum_string_utf8_bytes": 65_536,
    "maximum_total_string_utf8_bytes": 131_072,
    "maximum_integer_characters": 32,
    "allow_floats": False,
    "expected_case_count": EXPECTED_CASE_COUNT,
    "expected_mutation_count": 90,
    "minimum_mutations_per_case": 2,
    "maximum_mutations_per_case": 16,
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
EXPECTED_SOURCE_BINDING = {
    "fence_language": "json",
    "fence_capture": (
        "content_between_exact_json_fence_markers_excluding_terminal_newline"
    ),
    "path_root": "repository",
    "sha256_encoding": "lowercase_hex",
}
EXPECTED_DECISION_SET_BINDING = {
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
    "projection_byte_length": 16_383,
    "projection_sha256": (
        "40d52a56a3d561e118865f823cf55d1172e25b64f600e413e3635bf1b511f4f5"
    ),
    "sha256": "794c90203c662f1e12d78844c8ac8dcfc0162b0d3813b7df04cbe2e10cdd835a",
    "effect": "NON_ACCEPTING_EXACT_SUBJECT_BINDING_ONLY",
}

CORPUS_JSON_LIMITS = JsonLimits(
    maximum_bytes=MAX_CORPUS_BYTES,
    maximum_depth=32,
    maximum_items=100_000,
    maximum_object_members=4_096,
    maximum_array_items=4_096,
    maximum_key_utf8_bytes=256,
    maximum_string_utf8_bytes=65_536,
    maximum_total_string_utf8_bytes=MAX_CORPUS_BYTES,
    maximum_integer_chars=32,
    maximum_float_chars=64,
    allow_floats=False,
)
ENGINE_OUTPUT_JSON_LIMITS = JsonLimits(
    maximum_bytes=MAX_ENGINE_OUTPUT_BYTES,
    maximum_depth=32,
    maximum_items=100_000,
    maximum_object_members=4_096,
    maximum_array_items=4_096,
    maximum_key_utf8_bytes=256,
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
    maximum_key_utf8_bytes=256,
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
    maximum_key_utf8_bytes=256,
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
    if len(pointer.encode("utf-8")) > 1_024 or not pointer.startswith("/"):
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
    if binding != EXPECTED_DECISION_SET_BINDING:
        _fail("decision_set_binding is not the closed current non-accepting subject")
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
        for key in ("schema", "digest_algorithm", "domain_hex", "sha256")
    }
    if registry.get("decision_set") != registered_identity:
        _fail("decision registry has a different decision-set identity")
    review_subject = _object(
        registry.get("review_packet_subject"), "review_packet_subject"
    )
    if review_subject.get("decision_set") != registered_identity:
        _fail("review subject has a different decision-set identity")

    raw_decisions = _array(registry.get("decisions"), "decision registry decisions")
    projected_decisions: list[dict[str, Any]] = []
    identities: dict[str, tuple[str, int, str]] = {}
    member_names = binding["decision_members"]
    for index, raw_decision in enumerate(raw_decisions):
        decision = _object(raw_decision, f"decision registry decision {index}")
        missing = [name for name in member_names if name not in decision]
        if missing:
            _fail(f"decision registry decision {index} lacks projection members")
        projection = {name: decision[name] for name in member_names}
        projected_decisions.append(projection)
        decision_id = _string(decision.get("id"), f"decision {index} id")
        path = _string(decision.get("path"), f"decision {decision_id} path")
        byte_length = _positive_integer(
            decision.get("bytes"), f"decision {decision_id} bytes"
        )
        digest = _string(
            decision.get("content_sha256"),
            f"decision {decision_id} content_sha256",
        )
        if not HEX64.fullmatch(digest) or decision_id in identities:
            _fail("decision identities are duplicate or not lowercase SHA-256")
        identities[decision_id] = (path, byte_length, digest)

    projection = {
        "schema": binding["schema"],
        "candidate": registry.get("candidate"),
        "wire_version": registry.get("wire_version"),
        "review_policy": registry.get("review_policy"),
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
    return identities


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
    if not CASE_ID.fullmatch(mutation_id) or mutation_id in mutation_ids:
        _fail(f"{case_label} has a duplicate or invalid mutation id")
    mutation_ids.add(mutation_id)
    purpose = _string(mutation["purpose"], f"mutation {mutation_id} purpose")
    if len(purpose.encode("utf-8")) > 512:
        _fail(f"mutation {mutation_id} purpose exceeds its bound")
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
    _validate_expected_diagnostics(
        mutation["expected_diagnostics"],
        registry=registry,
        label=f"mutation {mutation_id} diagnostics",
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
        _fail("corpus does not contain exactly 22 cases")
    case_ids: set[str] = set()
    mutation_ids: set[str] = set()
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
        if not CASE_ID.fullmatch(case_id) or case_id in case_ids:
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
        _validate_expected_diagnostics(
            case["expected_diagnostics"],
            registry=registry,
            label=f"case {case_id} diagnostics",
        )
        if len(_canonical_json(case["bounded_fixture"])) > MAX_FIXTURE_BYTES:
            _fail(f"case {case_id} fixture exceeds its byte bound")

        source = _object(case["source"], f"case {case_id} source")
        _exact_keys(
            source,
            {
                "adr",
                "path",
                "json_fence_ordinal",
                "adr_byte_length",
                "adr_sha256",
                "fence_byte_length",
                "fence_sha256",
            },
            f"case {case_id} source",
        )
        path = _string(source["path"], f"case {case_id} source path")
        match = ADR_PATH.fullmatch(path)
        adr = _string(source["adr"], f"case {case_id} source ADR")
        if match is None or adr != f"ADR-{match.group(1)[1:]}":
            _fail(f"case {case_id} source ADR and path disagree")
        ordinal = _positive_integer(
            source["json_fence_ordinal"], f"case {case_id} source ordinal"
        )
        coordinates.append((path, ordinal))
        for name in ("adr_byte_length", "fence_byte_length"):
            _positive_integer(source[name], f"case {case_id} source {name}")
        for name in ("adr_sha256", "fence_sha256"):
            digest = _string(source[name], f"case {case_id} source {name}")
            if not HEX64.fullmatch(digest):
                _fail(f"case {case_id} source {name} is not lowercase SHA-256")

        mutations = _array(case["mutations"], f"case {case_id} mutations")
        if not 2 <= len(mutations) <= 16:
            _fail(f"case {case_id} mutation count is outside 2..16")
        for mutation in mutations:
            validated_mutation = _validate_mutation(
                mutation,
                case_label=f"case {case_id}",
                mutation_ids=mutation_ids,
                registry=registry,
            )
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
    return cases, mutation_count


def _verify_source_bindings(
    cases: list[dict[str, Any]],
    decision_identities: dict[str, tuple[str, int, str]],
) -> list[dict[str, Any]]:
    by_path: dict[str, bytes] = {}
    declared_adr_identity: dict[str, tuple[int, str]] = {}
    source_identities: list[dict[str, Any]] = []
    covered: set[tuple[str, int]] = set()
    for case in cases:
        source = case["source"]
        adr = source["adr"]
        path = source["path"]
        decision_path, decision_bytes, decision_sha256 = decision_identities[adr]
        if (
            path != decision_path
            or source["adr_byte_length"] != decision_bytes
            or source["adr_sha256"] != decision_sha256
        ):
            _fail(f"case {case['id']} is not bound to its decision-set ADR identity")
        identity = (source["adr_byte_length"], source["adr_sha256"])
        if adr in declared_adr_identity and declared_adr_identity[adr] != identity:
            _fail(f"case {case['id']} disagrees about its ADR identity")
        declared_adr_identity[adr] = identity
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
        if len(adr_bytes) != identity[0] or _sha256(adr_bytes) != identity[1]:
            _fail(f"{adr} bytes do not match the corpus and decision set")
        fences = JSON_FENCE.findall(adr_bytes)
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
                "adr_byte_length": source["adr_byte_length"],
                "adr_sha256": source["adr_sha256"],
                "fence_byte_length": source["fence_byte_length"],
                "fence_sha256": source["fence_sha256"],
            }
        )
    if tuple(sorted(declared_adr_identity)) != EXPECTED_ADR_IDS:
        _fail("case source bindings do not cover exactly ADR-001 through ADR-011")
    if sum(len(value) for value in by_path.values()) > MAX_AGGREGATE_ADR_BYTES:
        _fail("ADR source corpus exceeds its aggregate byte bound")
    expected_coverage = {
        (path, ordinal)
        for path, content in by_path.items()
        for ordinal in range(1, len(JSON_FENCE.findall(content)) + 1)
    }
    if covered != expected_coverage:
        _fail("corpus does not cover every and only JSON fence in the eleven ADRs")
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
    if not claims or any(value is not False for value in claims.values()):
        _fail("claim_boundary must be nonempty and entirely false")
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
    altered_binding["decision_set_binding"]["sha256"] = "0" * 64
    _expect_failure(
        lambda: _prepare_corpus_value(b"{}", altered_binding),
        "altered decision-set binding",
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
