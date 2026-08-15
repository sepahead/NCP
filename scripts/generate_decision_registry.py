#!/usr/bin/env python3
"""Generate the non-normative NCP architecture-decision review registry.

The registry stays outside ``contract/``. It derives review status from exact ADR
bytes, structured role obligations, and bounded content-addressed review records.
The checks establish structural consistency only. They do not prove reviewer
authorship, role authority, independence, rebaseline authorization, or release
readiness.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import ipaddress
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn
from urllib.parse import urlsplit

from bounded_json import (
    BoundedJsonError,
    FileSnapshotLimits,
    JsonLimits,
    parse_json_bytes,
    read_bounded_regular_file,
    validate_native_json_tree,
)
from validate_evidence_schemas import (
    EvidenceSchemaError,
    validate_decision_registry_instance,
    validate_instance,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "adr" / "decision-registry.source.v1.json"
OUTPUT = ROOT / "docs" / "adr" / "decision-registry.proposed.v1.json"
SCHEMA = ROOT / "docs" / "adr" / "decision-registry.proposed.schema.v1.json"
CLOSURE_SOURCE = ROOT / "docs" / "adr" / "decision-closure.source.v1.json"
CLOSURE_SCHEMA = ROOT / "docs" / "adr" / "decision-closure.source.schema.v1.json"
REVIEW_PACKET = ROOT / "docs" / "adr" / "B01_REVIEW_PACKET.md"
PROMOTION_TARGET = ROOT / "contract" / "decision-registry.v1.json"
GIT = shutil.which("git")

SOURCE_SCHEMA = "ncp.proposed-decision-registry-source.v1"
OUTPUT_SCHEMA = "ncp.proposed-decision-registry.v1"
DECISION_SET_SCHEMA = "ncp.b01-decision-set.v1"
ADR_SOURCE_SET_SCHEMA = "ncp.b01-adr-source-set.v1"
REVIEW_POLICY_SCHEMA = "ncp.b01-review-policy.v1"
REVIEW_SUBJECT_SCHEMA = "ncp.b01-review-subject.v1"
REVIEW_PACKET_LIFECYCLE_SCHEMA = "ncp.b01-review-packet-lifecycle.v1"
DECISION_CLOSURE_SOURCE_SCHEMA = "ncp.b01-decision-closure-source.v1"
DECISION_CLOSURE_SCHEMA_ID = (
    "https://sepahead.github.io/NCP/schemas/decision-closure-source.v1.json"
)
DECISION_SET_DOMAIN = b"ncp.b01-decision-set.v1\x00"
ADR_SOURCE_SET_DOMAIN = b"ncp.b01-adr-source-set.v1\x00"
B03_ELIGIBILITY_SET_DOMAIN = b"ncp.b01-b03-eligibility-set.v1\x00"
GENERATOR = "scripts/generate_decision_registry.py"
SOURCE_RELATIVE = SOURCE.relative_to(ROOT).as_posix()
SCHEMA_RELATIVE = SCHEMA.relative_to(ROOT).as_posix()
CLOSURE_SOURCE_RELATIVE = CLOSURE_SOURCE.relative_to(ROOT).as_posix()
CLOSURE_SCHEMA_RELATIVE = CLOSURE_SCHEMA.relative_to(ROOT).as_posix()
EXPECTED_IDS = tuple(f"ADR-{number:03d}" for number in range(1, 12))
EXPECTED_DEFECTS = {f"D{number:02d}" for number in range(1, 21)}
ADR_MAIN_PATH = re.compile(
    r"docs/adr/(000[1-9]|001[01])-[a-z0-9]+(?:-[a-z0-9]+)*\.md\Z"
)
ADR_MODULE_PATH = re.compile(
    r"docs/adr/modules/adr-(00[1-9]|01[01])-[a-z0-9]+(?:-[a-z0-9]+)*\.md\Z"
)
EXPECTED_MODULE_PATHS = {
    **{identifier: () for identifier in EXPECTED_IDS},
    "ADR-004": (
        "docs/adr/modules/adr-004-cross-store-observer-closure-and-enrollment.md",
    ),
    "ADR-009": (
        "docs/adr/modules/adr-009-cross-store-producer-and-compromise-evidence.md",
    ),
}

MAX_JSON_BYTES = 2 * 1024 * 1024
MIN_ADR_MARKDOWN_BYTES = 1024
MAX_ADR_MARKDOWN_BYTES = 256 * 1024
MAX_ADR_CORPUS_BYTES = 2 * 1024 * 1024
MAX_ADR_MODULES_PER_DECISION = 8
MAX_EVIDENCE_BYTES = 1024 * 1024
MAX_TOTAL_EVIDENCE_BYTES = 16 * 1024 * 1024
MAX_UNIQUE_EVIDENCE_FILES = 1024
MAX_REVIEW_RECORDS = 256
MAX_CONDITIONS = 16
MAX_EVIDENCE_PER_CONDITION = 16
MAX_B03_LITERAL_INTEGER = 2**53 - 1
EVIDENCE_PREFIX = "evidence/implementation/reviews/B01/"
REGISTRY_JSON_LIMITS = JsonLimits(
    maximum_bytes=MAX_JSON_BYTES,
    maximum_depth=32,
    maximum_items=100_000,
    maximum_object_members=256,
    maximum_array_items=4096,
    maximum_key_utf8_bytes=128,
    maximum_string_utf8_bytes=4096,
    maximum_total_string_utf8_bytes=MAX_JSON_BYTES,
    maximum_integer_chars=128,
    maximum_float_chars=128,
    allow_floats=False,
)
ADR_FENCE_JSON_LIMITS = JsonLimits(
    maximum_bytes=131_072,
    maximum_depth=32,
    maximum_items=100_000,
    maximum_object_members=4_096,
    maximum_array_items=4096,
    maximum_key_utf8_bytes=128,
    maximum_string_utf8_bytes=65_536,
    maximum_total_string_utf8_bytes=131_072,
    maximum_integer_chars=32,
    maximum_float_chars=32,
    allow_floats=False,
)
REGISTRY_FILE_LIMITS = FileSnapshotLimits(
    minimum_bytes=1,
    maximum_bytes=MAX_JSON_BYTES,
)
EVIDENCE_FILE_LIMITS = FileSnapshotLimits(
    minimum_bytes=1,
    maximum_bytes=MAX_EVIDENCE_BYTES,
)

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ROLE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REVIEW_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,127}$")
CONDITION_ID = re.compile(r"^[A-Z0-9][A-Z0-9._-]{1,63}$")
SEMANTIC_CASE_ID = re.compile(r"^adr(?:00[1-9]|01[01])\.[a-z0-9][a-z0-9.-]*\.v1$")
SEMANTIC_PROFILE_ID = re.compile(r"^ADR(?:00[1-9]|01[01])_[A-Z0-9_]+_V1$")
EXPECTED_SEMANTIC_CASE_IDENTITIES = {
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
IDENTITY_URI = re.compile(r"^[a-z][a-z0-9+.-]*:[\x21-\x7e]+$")
DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")
RELATIVE_PATH = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$)).+$")
UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

SEMANTIC_CORPUS_SCHEMA = "ncp.b01-adr-example-semantics-corpus.v1"
SEMANTIC_CLOSURE_EVALUATION_SCHEMA = "ncp.b01-semantic-closure-evaluation.v1"
SEMANTIC_CORPUS_PATH = (
    "prototypes/b01-architecture-evidence/adr-example-semantics/corpus.v1.json"
)
EXPECTED_NO_EDGE_CLASSES = (
    "CONTROL_DEPENDENCY",
    "NCP_ATLAS_OWNER",
    "NCP_AUTHORITY_EDGE",
    "NCP_COMMANDER",
    "NCP_CONSUMER",
    "NCP_DOCUMENTATION_IMPORT_EDGE",
    "NCP_EVIDENCE_EDGE",
    "NCP_EXPORT_EDGE",
    "NCP_IMPLEMENTATION_EDGE",
    "NCP_PACKAGE_DEPENDENCY",
    "NCP_PEER",
    "NCP_RELEASE_EDGE",
    "NCP_ROLE_RECEIPT",
    "NCP_RUNTIME_EDGE",
    "NCP_SEMANTIC_EDGE",
    "NCP_WORK_AUTHORITY",
    "OBSERVATION_EDGE",
    "OBSERVER_GRANT_HOLDER",
    "PROTOCOL_SOURCE_OF_TRUTH",
)
EXPECTED_NO_EDGE_COMPONENTS = {
    "cortexel": {
        "prohibited_review_role_ids": {"cortexel-owner"},
        "prohibited_edge_classes": set(EXPECTED_NO_EDGE_CLASSES),
        "canonical_aliases": ("cortexel", "sepahead/cortexel"),
        "identity_match_profile": (
            "ASCII_CASEFOLD_SPLIT_ON_NON_ALNUM_TOKEN_EQUALS_COMPONENT_ID"
        ),
    }
}
EXPECTED_QUESTION_ANCHORS = {
    "ADR-001": (
        (
            "ADR-001-Q01",
            "docs/adr/0001-separate-simulation-and-plant-sessions.md#open-questions",
        ),
    ),
    "ADR-002": (
        (
            "ADR-002-Q01",
            "docs/adr/0002-contract-identity-and-release-authorization.md#open-questions",
        ),
    ),
    "ADR-003": (
        (
            "ADR-003-Q01",
            "docs/adr/0003-authenticated-production-ingress.md#open-questions",
        ),
    ),
    "ADR-004": (
        (
            "ADR-004-Q01",
            "docs/adr/0004-observer-attach-grants-and-revocation.md#open-questions",
        ),
    ),
    "ADR-005": (
        (
            "ADR-005-Q01",
            "docs/adr/0005-declared-stream-lifecycle.md#open-questions",
        ),
    ),
    "ADR-006": (
        (
            "ADR-006-Q01",
            "docs/adr/0006-body-issued-authority-and-time.md#open-questions",
        ),
    ),
    "ADR-007": (
        (
            "ADR-007-Q01",
            "docs/adr/0007-command-disposition-journal.md#illustrative-wire-example",
        ),
        (
            "ADR-007-Q02",
            "docs/adr/0007-command-disposition-journal.md#open-questions",
        ),
    ),
    "ADR-008": (
        (
            "ADR-008-Q01",
            "docs/adr/0008-extension-namespace-and-galadriel-separation.md#bounds-and-resource-behavior",
        ),
        (
            "ADR-008-Q02",
            "docs/adr/0008-extension-namespace-and-galadriel-separation.md#open-questions",
        ),
    ),
    "ADR-009": (
        (
            "ADR-009-Q01",
            "docs/adr/modules/adr-009-cross-store-producer-and-compromise-evidence.md#cross-store-producer-audience-retention-and-compromise-rules",
        ),
    ),
    "ADR-010": (
        (
            "ADR-010-Q01",
            "docs/adr/0010-plane-qos-retention-and-overload.md#bounds-and-resource-behavior",
        ),
        (
            "ADR-010-Q02",
            "docs/adr/0010-plane-qos-retention-and-overload.md#open-questions",
        ),
    ),
    "ADR-011": (
        (
            "ADR-011-Q01",
            "docs/adr/0011-ecosystem-topology-and-handover.md#open-questions",
        ),
    ),
}
B03_TEST_SUFFIXES_BY_KIND = {
    "BOUNDED_INTEGER": (
        "MIN-EQUALITY",
        "MAX-EQUALITY",
        "BELOW-MINIMUM",
        "ABOVE-MAXIMUM",
        "PREDICATE-REJECT",
        "OVERFLOW",
        "UNKNOWN-DEFAULT-REJECT",
    ),
    "EXACT_IDENTITY_SET": (
        "MIN-EQUALITY",
        "MAX-EQUALITY",
        "BELOW-MINIMUM",
        "ABOVE-MAXIMUM",
        "INELIGIBLE-MEMBER-REJECT",
        "PROHIBITED-MEMBER-REJECT",
        "OVERFLOW",
        "UNKNOWN-DEFAULT-REJECT",
    ),
}
ZERO_MINIMUM_BOUNDED_INTEGER_PARAMETERS = {
    ("ADR-005-Q01", "REORDER_LIMIT"),
}
EXPECTED_B03_PARAMETER_CONTRACT = {
    "schema": "ncp.b01-b03-parameter-contract.v1",
    "value_kinds": ["BOUNDED_INTEGER", "EXACT_IDENTITY_SET"],
    "envelope_fields": ["minimum", "maximum"],
    "literal_integer_encoding": (
        "NONNEGATIVE_JSON_SAFE_INTEGER_FOR_BOUNDED_INTEGER_AND_JSON_SAFE_"
        "CARDINALITY_FOR_EXACT_IDENTITY_SET"
    ),
    "validated_envelope": (
        "KIND_APPROPRIATE_LITERAL_MINIMUM_AND_FINITE_LITERAL_MAXIMUM_WITH_MINIMUM_"
        "LTE_MAXIMUM"
    ),
    "future_b03_allocation_binding": "OUTSIDE_B01_DECISION_SET",
    "future_allocation_constraint": (
        "MUST_REMAIN_WITHIN_ACCEPTED_ENVELOPE_AND_MUST_NOT_CHANGE_ACCEPTED_MEANING"
    ),
    "selection_predicate_binding": (
        "EXACT_PARAMETER_ID_SOURCE_ANCHOR_VALUE_KIND_PROFILE_AND_ELIGIBILITY"
    ),
    "selection_profile_semantics": {
        "B03_BOUNDED_INTEGER_SELECTION_V1": (
            "NONNEGATIVE_JSON_SAFE_INTEGER_WITHIN_INCLUSIVE_ACCEPTED_ENVELOPE"
        ),
        "B03_EXACT_IDENTITY_SET_SELECTION_V1": (
            "CANONICAL_UNIQUE_SET_SATISFYING_BOUND_SOURCE_PREDICATE_AND_OPTIONAL_"
            "EXACT_B01_UNIVERSE_WITH_GLOBAL_NO_EDGE_DENY"
        ),
    },
    "identity_set_measure": "CARDINALITY_OF_CANONICAL_UNIQUE_IDENTITIES",
    "identity_canonicalization": (
        "SOURCE_PREDICATE_GRAMMAR_THEN_RAW_BYTE_ASCENDING_UNIQUE"
    ),
    "identity_eligibility_binding": (
        "BOUND_SOURCE_PREDICATE_AND_OPTIONAL_EXACT_B01_UNIVERSE_WHEN_VALIDATED"
    ),
    "empty_identity_universe_semantics": (
        "BOUND_SOURCE_PREDICATE_IS_THE_ELIGIBILITY_AUTHORITY"
    ),
    "identity_eligibility_digest_algorithm": (
        "sha256(domain || u64be(projection_bytes) || projection)"
    ),
    "identity_eligibility_digest_domain_hex": B03_ELIGIBILITY_SET_DOMAIN.hex(),
    "identity_eligibility_projection_encoding": (
        "UTF8_JSON_SORTED_KEYS_COMPACT_ENSURE_ASCII_FALSE"
    ),
    "identity_eligibility_projection_members": [
        "eligible_identities",
        "parameter_id",
        "question_id",
        "value_kind",
    ],
    "future_identity_selection_constraint": (
        "CANONICAL_SET_SATISFYING_BOUND_SOURCE_PREDICATE_OPTIONAL_EXACT_UNIVERSE_"
        "AND_CARDINALITY_ENVELOPE"
    ),
    "global_no_edge_inheritance": (
        "ALL_SELECTION_PREDICATES_REJECT_MATCHED_EXCLUDED_COMPONENT_ALIASES"
    ),
    "future_b03_selection_verifier": (
        "REQUIRED_OUTSIDE_B01_DECISION_SET_BEFORE_ALLOCATION"
    ),
    "absence_and_unknown": "REJECT_BEFORE_ALLOCATION",
    "required_test_suffixes_by_value_kind": {
        kind: list(suffixes) for kind, suffixes in B03_TEST_SUFFIXES_BY_KIND.items()
    },
}
EXPECTED_B03_BINDINGS = {
    "ADR-002-Q01": (
        "protocol-reviewer",
        (
            ("STABLE_CORE_FILE_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("STABLE_CORE_PROJECTION_PROFILE_IDENTITIES", "EXACT_IDENTITY_SET"),
        ),
    ),
    "ADR-005-Q01": (
        "distributed-systems-reviewer",
        (
            ("INTERFACE_NAME_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("SEQUENCE_LIMIT", "BOUNDED_INTEGER"),
            ("REORDER_LIMIT", "BOUNDED_INTEGER"),
            ("TOMBSTONE_CAPACITY", "BOUNDED_INTEGER"),
        ),
    ),
    "ADR-006-Q01": (
        "distributed-systems-reviewer",
        (
            ("IMPLEMENTATION_NAME_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("AUTHORITY_STATE_CAPACITY", "BOUNDED_INTEGER"),
        ),
    ),
    "ADR-007-Q02": (
        "plant-safety-reviewer",
        (
            ("IMPLEMENTATION_NAME_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("JOURNAL_ENTRY_CAPACITY", "BOUNDED_INTEGER"),
            ("JOURNAL_AGGREGATE_BYTES", "BOUNDED_INTEGER"),
            ("JOURNAL_RETENTION_NS", "BOUNDED_INTEGER"),
        ),
    ),
    "ADR-008-Q02": (
        "protocol-reviewer",
        (
            ("NAMESPACE_OWNER_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("SCHEMA_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("BODY_AUTHORITY_PROVENANCE_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("ASSESSOR_REPLAY_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("ADAPTER_PROOF_REFERENCE_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("CHUNK_FRAME_PROFILE_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("ROUTE_ENCODING_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("PARSER_PROFILE_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("CALLBACK_PROFILE_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("RESOURCE_PROFILE_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("ACTIVATION_LIFETIME_NS_MAX", "BOUNDED_INTEGER"),
            ("CHUNK_COUNT_MAX", "BOUNDED_INTEGER"),
        ),
    ),
    "ADR-009-Q01": (
        "security-reviewer",
        (
            ("CROSS_STORE_EXACT_OPENING_MAX_BYTES", "BOUNDED_INTEGER"),
            ("CROSS_STORE_CAPSULE_PROFILE_IDENTITIES", "EXACT_IDENTITY_SET"),
        ),
    ),
    "ADR-010-Q02": (
        "real-time-performance-reviewer",
        (
            ("QOS_PROFILE_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("QUEUE_ITEM_CAPACITY_MAX", "BOUNDED_INTEGER"),
            ("QUEUE_AGGREGATE_BYTES_MAX", "BOUNDED_INTEGER"),
            ("ADMISSION_DEADLINE_NS_MAX", "BOUNDED_INTEGER"),
            ("RETENTION_NS_MAX", "BOUNDED_INTEGER"),
            ("ATTEMPT_COUNT_MAX", "BOUNDED_INTEGER"),
            ("PENDING_REQUEST_CAPACITY_MAX", "BOUNDED_INTEGER"),
            ("GAP_WAIT_NS_MAX", "BOUNDED_INTEGER"),
            ("WORK_RESOLUTION_NS_MAX", "BOUNDED_INTEGER"),
            ("ACTIVE_BURST_MAX", "BOUNDED_INTEGER"),
        ),
    ),
    "ADR-011-Q01": (
        "release-package-tooling-reviewer",
        (
            ("EXTENSION_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("PACKAGE_FEATURE_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("CONSUMER_INVENTORY_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("EFFECT_PATH_DESCRIPTOR_PROFILE_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("EFFECT_PATH_RESERVATION_CAPACITY", "BOUNDED_INTEGER"),
            ("HANDOVER_DEADLINE_NS", "BOUNDED_INTEGER"),
        ),
    ),
}
EXPECTED_SEMANTIC_EXAMPLE_CONTRACT = {
    "schema": SEMANTIC_CORPUS_SCHEMA,
    "coverage": "EVERY_MAIN_ADR_JSON_FENCE_HAS_A_SOURCE_BOUND_CASE_AND_REJECTION_OBSERVATION",
    "rejection_observation": "NEGATIVE_CASE_OR_BOUNDED_MUTATION",
    "engine_requirement": "REQUIRED_BY_COMPLETE_LOCAL_GATE_OUTSIDE_REGISTRY_CLOSURE",
    "positive_authority": "NON_AUTHORIZING_EXCERPT_NOT_PRODUCTION_ADMISSION",
    "external_effect": "NONE_LOCAL_CHALLENGE_EVIDENCE_ONLY",
}
EXPECTED_DIAGNOSTIC_REGISTRY_COUNT = 107
EXPECTED_DIAGNOSTIC_REGISTRY_BYTE_LENGTH = 3_543
EXPECTED_DIAGNOSTIC_REGISTRY_SHA256 = (
    "f8e704286f7a0c30b6525e5835bcf2d46e21e5c1bc8db7bbef928cff17208d2d"
)
EXPECTED_SEMANTIC_SOURCE_BINDING = {
    "fence_capture": (
        "content_between_top_level_exact_json_fence_lines_excluding_one_terminal_line_ending"
    ),
    "fence_language": "json",
    "path_root": "repository",
    "sha256_encoding": "lowercase_hex",
}
EXPECTED_SEMANTIC_LIMITS = {
    "allow_floats": False,
    "engine_timeout_seconds": 120,
    "expected_case_count": 25,
    "expected_mutation_count": 132,
    "maximum_adr_bytes": 262_144,
    "maximum_aggregate_adr_bytes": 2_097_152,
    "maximum_array_items": 4_096,
    "maximum_corpus_bytes": 262_144,
    "maximum_engine_output_bytes": 262_144,
    "maximum_integer_characters": 32,
    "maximum_json_depth": 32,
    "maximum_json_fence_bytes": 131_072,
    "maximum_fixture_bytes": 16_384,
    "maximum_json_nodes": 100_000,
    "maximum_key_utf8_bytes": 128,
    "maximum_mutations_per_case": 24,
    "maximum_object_members": 4_096,
    "maximum_string_utf8_bytes": 65_536,
    "maximum_total_string_utf8_bytes": 131_072,
    "minimum_mutations_per_case": 2,
}
EXPECTED_SEMANTIC_CLOSED_VALUES = {
    "patch_operation": ["ADD", "REMOVE", "REPLACE"],
    "patch_target": ["BOUNDED_FIXTURE", "DOCUMENT"],
    "polarity": ["NEGATIVE", "POSITIVE"],
    "production_admission": ["NOT_APPLICABLE", "NOT_EVALUATED", "REJECT"],
    "profile_result": [
        "MATCH_NON_AUTHORIZING_EXCERPT",
        "MATCH_NON_WIRE_EXCERPT",
        "REJECT",
    ],
    "scope": [
        "AUTHENTICATED_WIRE_OBJECT",
        "DECODED_HEADER_FRAGMENT",
        "NON_NCP_INTENT_CORRELATION_FRAGMENT",
        "NON_WIRE_INTERNAL_STATE",
        "PROPOSED_EXTENSION_ENVELOPE",
        "PROPOSED_SEMANTIC_PROJECTION",
        "PROPOSED_WIRE_FRAGMENT",
    ],
}
SEMANTIC_CORPUS_JSON_LIMITS = JsonLimits(
    maximum_bytes=EXPECTED_SEMANTIC_LIMITS["maximum_corpus_bytes"],
    maximum_depth=EXPECTED_SEMANTIC_LIMITS["maximum_json_depth"],
    maximum_items=EXPECTED_SEMANTIC_LIMITS["maximum_json_nodes"],
    maximum_object_members=EXPECTED_SEMANTIC_LIMITS["maximum_object_members"],
    maximum_array_items=EXPECTED_SEMANTIC_LIMITS["maximum_array_items"],
    maximum_key_utf8_bytes=EXPECTED_SEMANTIC_LIMITS["maximum_key_utf8_bytes"],
    maximum_string_utf8_bytes=EXPECTED_SEMANTIC_LIMITS["maximum_string_utf8_bytes"],
    maximum_total_string_utf8_bytes=EXPECTED_SEMANTIC_LIMITS[
        "maximum_total_string_utf8_bytes"
    ],
    maximum_integer_chars=EXPECTED_SEMANTIC_LIMITS["maximum_integer_characters"],
    maximum_float_chars=EXPECTED_SEMANTIC_LIMITS["maximum_integer_characters"],
    allow_floats=False,
)
SEMANTIC_OBJECT_JSON_LIMITS = JsonLimits(
    maximum_bytes=EXPECTED_SEMANTIC_LIMITS["maximum_json_fence_bytes"],
    maximum_depth=EXPECTED_SEMANTIC_LIMITS["maximum_json_depth"],
    maximum_items=EXPECTED_SEMANTIC_LIMITS["maximum_json_nodes"],
    maximum_object_members=EXPECTED_SEMANTIC_LIMITS["maximum_object_members"],
    maximum_array_items=EXPECTED_SEMANTIC_LIMITS["maximum_array_items"],
    maximum_key_utf8_bytes=EXPECTED_SEMANTIC_LIMITS["maximum_key_utf8_bytes"],
    maximum_string_utf8_bytes=EXPECTED_SEMANTIC_LIMITS["maximum_string_utf8_bytes"],
    maximum_total_string_utf8_bytes=EXPECTED_SEMANTIC_LIMITS[
        "maximum_total_string_utf8_bytes"
    ],
    maximum_integer_chars=EXPECTED_SEMANTIC_LIMITS["maximum_integer_characters"],
    maximum_float_chars=EXPECTED_SEMANTIC_LIMITS["maximum_integer_characters"],
    allow_floats=False,
)
DECISION_PROJECTION_MEMBERS = (
    "id",
    "title",
    "path",
    "module_paths",
    "content_sha256",
    "bytes",
    "source_set",
    "required_reviews",
    "defect_ids",
)
DECISION_SET_PROJECTION_MEMBERS = (
    "schema",
    "candidate",
    "wire_version",
    "review_policy",
    "semantic_closure",
    "decisions",
)

REQUIRED_SECTIONS = (
    "## Context",
    "## Proposed decision",
    "## Rejected alternatives",
    "## Invalid or hostile example",
    "## Actors and state transitions",
    "## Bounds and resource behavior",
    "## Threat and hazard analysis",
    "## Formal properties",
    "## Migration",
    "## Operational recovery",
    "## Compatibility and rollback",
    "## Open questions",
    "## Ten-lens review",
    "## Ratification record",
)

INVARIANT_STATUS = "- Decision status: derived from the non-normative decision registry"
INVARIANT_NORMATIVE_EFFECT = "- Normative effect before authorized N01 promotion: none"
INVARIANT_RATIFICATIONS = (
    (
        "The non-normative decision registry records exact review evidence and "
        "derives the\ncurrent decision status."
    ),
    (
        "The non-normative registry derives review status; review changes do not "
        "mutate\nthis invariant text."
    ),
    "The non-normative registry derives review status; these invariants stay fixed.",
)
CLAIM_BOUNDARY = (
    "This generated registry records non-normative architecture decisions and "
    "structurally checked review claims. It cannot prove external authorship, role "
    "authority, or independence. It cannot satisfy B01 by itself, authorize the "
    "pre-release rebaseline or publication, or grant runtime identity, authority, "
    "plant action, safety, interoperability, or a scientific claim."
)
SOURCE_CLAIM_BOUNDARY = (
    "This source records non-normative architecture decisions and bounded review "
    "claims. Its structural checks cannot prove external authorship, role authority, "
    "or independence. It cannot change the normative contract, authorize a rebaseline "
    "or release, satisfy B01 by itself, or certify an implementation or deployment."
)
CLOSURE_CLAIM_BOUNDARY = (
    "This source records local, non-normative semantic-closure requirements for "
    "B01. It cannot accept an ADR, change the wire contract, prove parser "
    "independence, authorize promotion or release, grant runtime authority, or "
    "satisfy external evidence gates."
)

SubjectResolver = Callable[[str, str], tuple[str, bytes]]


class RegistryError(ValueError):
    """The non-normative decision registry is malformed or overclaims status."""


def fail(message: str) -> NoReturn:
    raise RegistryError(message)


def extract_exact_json_fences(text: str, *, label: str) -> list[str]:
    """Return top-level exact ```json fences under the closed B01 grammar."""
    fences: list[str] = []
    state: tuple[str, int] | None = None
    line_start = 0
    while line_start < len(text):
        line_end = text.find("\n", line_start)
        if line_end < 0:
            line_end = len(text)
        logical_end = line_end
        if logical_end > line_start and text[logical_end - 1] == "\r":
            logical_end -= 1
        line = text[line_start:logical_end]
        next_line = line_end + 1 if line_end < len(text) else len(text)

        if state is None and line == "```json":
            if line_end == len(text):
                fail(f"{label} JSON fence opener has no following content line")
            state = ("json", next_line)
        elif state is None and line.startswith("```"):
            state = ("other", 0)
        elif state is not None and state[0] == "json" and line == "```":
            content_end = line_start
            if content_end > state[1] and text[content_end - 1] == "\n":
                content_end -= 1
                if content_end > state[1] and text[content_end - 1] == "\r":
                    content_end -= 1
            fences.append(text[state[1] : content_end])
            state = None
        elif state is not None and state[0] == "other" and line == "```":
            state = None
        line_start = next_line

    if state is not None:
        fail(f"{label} contains an unclosed Markdown fence")
    return fences


def load_json(path: Path, *, maximum_bytes: int = MAX_JSON_BYTES) -> dict[str, Any]:
    try:
        relative = path.relative_to(ROOT).as_posix()
    except ValueError:
        relative = str(path)
    try:
        content = read_bounded_regular_file(
            path,
            limits=FileSnapshotLimits(
                minimum_bytes=1,
                maximum_bytes=maximum_bytes,
            ),
            label=relative,
        )
    except BoundedJsonError as error:
        fail(str(error))
    return load_json_bytes(
        content,
        relative,
        maximum_bytes=maximum_bytes,
    )


def load_json_bytes(
    content: bytes, path: str, *, maximum_bytes: int = MAX_JSON_BYTES
) -> dict[str, Any]:
    limits = (
        REGISTRY_JSON_LIMITS
        if maximum_bytes == MAX_JSON_BYTES
        else JsonLimits(
            maximum_bytes=maximum_bytes,
            maximum_depth=REGISTRY_JSON_LIMITS.maximum_depth,
            maximum_items=REGISTRY_JSON_LIMITS.maximum_items,
            maximum_object_members=REGISTRY_JSON_LIMITS.maximum_object_members,
            maximum_array_items=REGISTRY_JSON_LIMITS.maximum_array_items,
            maximum_key_utf8_bytes=REGISTRY_JSON_LIMITS.maximum_key_utf8_bytes,
            maximum_string_utf8_bytes=REGISTRY_JSON_LIMITS.maximum_string_utf8_bytes,
            maximum_total_string_utf8_bytes=maximum_bytes,
            maximum_integer_chars=REGISTRY_JSON_LIMITS.maximum_integer_chars,
            maximum_float_chars=REGISTRY_JSON_LIMITS.maximum_float_chars,
            allow_floats=False,
        )
    )
    try:
        value = parse_json_bytes(
            content,
            limits=limits,
            label=path,
        )
    except BoundedJsonError as error:
        fail(f"cannot parse {path}: {error}")
    if not isinstance(value, dict):
        fail(f"{path} must contain one JSON object")
    return value


def parse_json_fence(
    text: str,
    *,
    label: str,
    limits: JsonLimits,
) -> Any:
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as error:
        fail(f"{label} is not Unicode scalar text: {error}")
    try:
        return parse_json_bytes(
            encoded,
            limits=limits,
            label=label,
        )
    except BoundedJsonError as error:
        fail(str(error))


def source_bytes(source: dict[str, Any]) -> bytes:
    return (json.dumps(source, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def b03_eligibility_set_sha256(
    question_id: str,
    parameter_id: str,
    eligible_identities: list[str],
) -> str:
    projection = {
        "eligible_identities": eligible_identities,
        "parameter_id": parameter_id,
        "question_id": question_id,
        "value_kind": "EXACT_IDENTITY_SET",
    }
    payload = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(
        B03_ELIGIBILITY_SET_DOMAIN + len(payload).to_bytes(8, "big") + payload
    )


def exact_keys(value: Any, expected: set[str], path: str) -> None:
    if not isinstance(value, dict):
        fail(f"{path} must be an object")
    actual = set(value)
    if actual != expected:
        fail(
            f"{path} keys differ: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def bounded_string(
    value: Any, path: str, *, minimum: int = 1, maximum: int = 1024
) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        fail(f"{path} must be a string of length {minimum}..{maximum}")
    if "\x00" in value:
        fail(f"{path} contains NUL")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        fail(f"{path} is not Unicode scalar text: {error}")
    return value


def bounded_integer(
    value: Any, path: str, *, minimum: int = 0, maximum: int = 2**53 - 1
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        fail(f"{path} must be an integer in {minimum}..{maximum}")
    return value


def relative_path(value: Any, path: str) -> str:
    text = bounded_string(value, path, maximum=256)
    if (
        not RELATIVE_PATH.fullmatch(text)
        or text == "."
        or "\\" in text
        or any(ord(character) < 0x20 for character in text)
        or PurePosixPath(text).as_posix() != text
    ):
        fail(f"{path} must be a safe repository-relative POSIX path")
    return text


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def stat_fingerprint(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        stat.S_IFMT(value.st_mode),
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def read_physical_regular_file(
    repository_root: Path,
    repository_path: str,
    *,
    maximum_bytes: int,
    label: str,
    phase_hook: Callable[[str], None] | None = None,
) -> bytes:
    """Read one bounded regular inode without following a repository-path symlink."""

    relative = relative_path(repository_path, label)
    components = PurePosixPath(relative).parts
    if not components:
        fail(f"{label} must identify a repository file")
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if (
        no_follow is None
        or directory is None
        or os.open not in os.supports_dir_fd
        or os.stat not in os.supports_dir_fd
    ):
        fail(f"{label} cannot be checked because required dirfd operations are absent")
    root = Path(repository_root)
    try:
        root_lstat = root.lstat()
    except OSError as error:
        fail(f"{label} repository root cannot be inspected: {error}")
    if root.is_symlink() or not stat.S_ISDIR(root_lstat.st_mode):
        fail(f"{label} repository root must be one physical directory")

    directory_flags = os.O_RDONLY | directory | no_follow | getattr(os, "O_CLOEXEC", 0)
    descriptors: list[int] = []
    file_descriptor = -1
    try:
        descriptors.append(os.open(root, directory_flags))
        opened_root = os.fstat(descriptors[0])
        if not stat.S_ISDIR(opened_root.st_mode) or stat_fingerprint(
            opened_root
        ) != stat_fingerprint(root_lstat):
            fail(f"{label} repository root changed during physical traversal")
        for component in components[:-1]:
            parent_descriptor = descriptors[-1]
            child_descriptor = os.open(
                component,
                directory_flags,
                dir_fd=parent_descriptor,
            )
            child_stat = os.fstat(child_descriptor)
            listed_stat = os.stat(
                component,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if not stat.S_ISDIR(child_stat.st_mode) or stat_fingerprint(
                child_stat
            ) != stat_fingerprint(listed_stat):
                fail(f"{label} ancestor changed during physical traversal")
            descriptors.append(child_descriptor)

        parent_descriptor = descriptors[-1]
        leaf = components[-1]
        if phase_hook is not None:
            phase_hook("parent-opened")
        before = os.stat(leaf, dir_fd=parent_descriptor, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            fail(f"{label} must be one non-hard-linked physical regular file")
        if not 1 <= before.st_size <= maximum_bytes:
            fail(f"{label} byte size is outside 1..{maximum_bytes}")
        file_descriptor = os.open(
            leaf,
            os.O_RDONLY | no_follow | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(file_descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or stat_fingerprint(opened) != stat_fingerprint(before)
        ):
            fail(f"{label} changed before its physical inode was opened")
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(file_descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(file_descriptor)
        if phase_hook is not None:
            phase_hook("read-complete")
        final = os.stat(leaf, dir_fd=parent_descriptor, follow_symlinks=False)
        if stat_fingerprint(after) != stat_fingerprint(opened) or stat_fingerprint(
            final
        ) != stat_fingerprint(opened):
            fail(f"{label} changed while its bytes were read")
        final_root = root.lstat()
        if stat_fingerprint(final_root) != stat_fingerprint(opened_root):
            fail(f"{label} repository root changed while its bytes were read")
        for index, component in enumerate(components[:-1]):
            final_directory = os.stat(
                component,
                dir_fd=descriptors[index],
                follow_symlinks=False,
            )
            if stat_fingerprint(final_directory) != stat_fingerprint(
                os.fstat(descriptors[index + 1])
            ):
                fail(f"{label} ancestor changed while its bytes were read")
        if not 1 <= len(content) <= maximum_bytes:
            fail(f"{label} byte size is outside 1..{maximum_bytes}")
        return content
    except OSError as error:
        fail(f"{label} cannot be read as a physical regular file: {error}")
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def read_repository_regular_file(
    repository_path: str, *, maximum_bytes: int, label: str
) -> bytes:
    return read_physical_regular_file(
        ROOT,
        repository_path,
        maximum_bytes=maximum_bytes,
        label=label,
    )


def repository_file_identity(
    path: Path,
    *,
    maximum_bytes: int = MAX_JSON_BYTES,
    content_override: bytes | None = None,
) -> dict[str, Any]:
    try:
        relative = path.relative_to(ROOT).as_posix()
    except ValueError:
        fail("review-policy path is outside the repository")
    if content_override is None:
        try:
            content = read_bounded_regular_file(
                path,
                limits=FileSnapshotLimits(
                    minimum_bytes=1,
                    maximum_bytes=maximum_bytes,
                ),
                label=relative,
            )
        except BoundedJsonError as error:
            fail(str(error))
    else:
        if type(content_override) is not bytes:
            fail(f"{relative} content override must be native bytes")
        content = content_override
    if not 1 <= len(content) <= maximum_bytes:
        fail(f"{relative} byte size is outside 1..{maximum_bytes}")
    return {
        "path": relative,
        "sha256": sha256_bytes(content),
        "bytes": len(content),
    }


def review_policy(
    policy_overrides: dict[str, bytes] | None = None,
) -> dict[str, Any]:
    overrides = policy_overrides or {}
    generator_relative = GENERATOR
    schema_relative = SCHEMA_RELATIVE
    unknown = set(overrides) - {generator_relative, schema_relative}
    if unknown:
        fail(f"unknown review-policy override paths: {sorted(unknown)}")
    return {
        "schema": REVIEW_POLICY_SCHEMA,
        "source_schema": SOURCE_SCHEMA,
        "output_schema": OUTPUT_SCHEMA,
        "generator": repository_file_identity(
            ROOT / generator_relative,
            content_override=overrides.get(generator_relative),
        ),
        "output_json_schema": repository_file_identity(
            SCHEMA,
            content_override=overrides.get(schema_relative),
        ),
    }


def load_closure_requirements(
    generated: list[dict[str, Any]],
    *,
    source_override: dict[str, Any] | None = None,
    schema_override: bytes | None = None,
) -> dict[str, Any]:
    """Load and bind acyclic semantic-closure requirements.

    The source declares stable requirements and paths only. The corpus is
    evaluated after the decision set exists, so it cannot become a digest ancestor
    of itself. Future B03 selections remain outside the B01 decision-set identity.
    """

    if source_override is None:
        try:
            closure_source_content = read_bounded_regular_file(
                CLOSURE_SOURCE,
                limits=REGISTRY_FILE_LIMITS,
                label=CLOSURE_SOURCE_RELATIVE,
            )
        except BoundedJsonError as error:
            fail(str(error))
        closure_source = load_json_bytes(
            closure_source_content,
            CLOSURE_SOURCE_RELATIVE,
        )
    else:
        try:
            validate_native_json_tree(
                source_override,
                limits=REGISTRY_JSON_LIMITS,
                label="decision closure source override",
            )
        except BoundedJsonError as error:
            fail(str(error))
        closure_source = copy.deepcopy(source_override)
        closure_source_content = source_bytes(closure_source)

    if schema_override is None:
        try:
            closure_schema_content = read_bounded_regular_file(
                CLOSURE_SCHEMA,
                limits=REGISTRY_FILE_LIMITS,
                label=CLOSURE_SCHEMA_RELATIVE,
            )
        except BoundedJsonError as error:
            fail(str(error))
    else:
        if (
            type(schema_override) is not bytes
            or not 1 <= len(schema_override) <= MAX_JSON_BYTES
        ):
            fail("decision closure schema override must contain bounded native bytes")
        closure_schema_content = schema_override
    closure_schema = load_json_bytes(
        closure_schema_content,
        CLOSURE_SCHEMA_RELATIVE,
    )
    try:
        validate_instance(
            closure_schema,
            closure_source,
            "decision closure source",
            expected_schema_id=DECISION_CLOSURE_SCHEMA_ID,
        )
    except EvidenceSchemaError as error:
        fail(str(error))

    exact_keys(
        closure_source,
        {
            "schema",
            "normative",
            "candidate",
            "wire_version",
            "task",
            "claim_boundary",
            "semantic_example_contract",
            "b03_parameter_contract",
            "excluded_no_edge_components",
            "decisions",
        },
        "closure",
    )
    if closure_source["schema"] != DECISION_CLOSURE_SOURCE_SCHEMA:
        fail("closure.schema is not the B01 decision-closure source schema")
    if closure_source["normative"] is not False:
        fail("closure.normative must be false")
    if (
        closure_source["candidate"] != "1.0.0-rc.1"
        or closure_source["wire_version"] != "1.0"
        or closure_source["task"] != "B01"
    ):
        fail("closure candidate, wire version, or task differs from B01")
    if closure_source["claim_boundary"] != CLOSURE_CLAIM_BOUNDARY:
        fail("closure.claim_boundary differs from the fail-closed boundary")
    if (
        closure_source["semantic_example_contract"]
        != EXPECTED_SEMANTIC_EXAMPLE_CONTRACT
    ):
        fail("closure.semantic_example_contract differs from the bounded contract")
    if closure_source["b03_parameter_contract"] != EXPECTED_B03_PARAMETER_CONTRACT:
        fail("closure.b03_parameter_contract differs from the fail-closed contract")

    required_role_ids = {
        requirement["role_id"]
        for decision in generated
        for requirement in decision["required_reviews"]
    }
    components = closure_source["excluded_no_edge_components"]
    component_ids: list[str] = []
    prohibited_roles: set[str] = set()
    observed_components: dict[str, dict[str, Any]] = {}
    for index, component in enumerate(components):
        path = f"closure.excluded_no_edge_components[{index}]"
        exact_keys(
            component,
            {
                "component_id",
                "prohibited_review_role_ids",
                "prohibited_edge_classes",
                "canonical_aliases",
                "identity_match_profile",
            },
            path,
        )
        component_id = bounded_string(
            component["component_id"], f"{path}.component_id", maximum=64
        )
        if not ROLE_ID.fullmatch(component_id):
            fail(f"{path}.component_id is not canonical lowercase kebab case")
        component_ids.append(component_id)
        role_values = component["prohibited_review_role_ids"]
        edge_values = component["prohibited_edge_classes"]
        canonical_aliases = component["canonical_aliases"]
        if not isinstance(role_values, list) or any(
            not isinstance(role, str) or ROLE_ID.fullmatch(role) is None
            for role in role_values
        ):
            fail(f"{path}.prohibited_review_role_ids contains an invalid role")
        if not isinstance(edge_values, list) or any(
            not isinstance(edge_class, str) for edge_class in edge_values
        ):
            fail(f"{path}.prohibited_edge_classes must contain strings")
        roles = set(role_values)
        edge_classes = set(edge_values)
        if len(roles) != len(role_values):
            fail(f"{path}.prohibited_review_role_ids contains duplicates")
        if len(edge_classes) != len(edge_values):
            fail(f"{path}.prohibited_edge_classes contains duplicates")
        if tuple(edge_values) != EXPECTED_NO_EDGE_CLASSES:
            fail(
                f"{path}.prohibited_edge_classes differs from the exact "
                "ASCII-ordered prohibited-edge taxonomy"
            )
        if (
            canonical_aliases != ["cortexel", "sepahead/cortexel"]
            or component["identity_match_profile"]
            != "ASCII_CASEFOLD_SPLIT_ON_NON_ALNUM_TOKEN_EQUALS_COMPONENT_ID"
        ):
            fail(f"{path} has an incomplete canonical identity exclusion profile")
        prohibited_roles.update(roles)
        observed_components[component_id] = {
            "prohibited_review_role_ids": roles,
            "prohibited_edge_classes": edge_classes,
            "canonical_aliases": tuple(canonical_aliases),
            "identity_match_profile": component["identity_match_profile"],
        }
    if len(component_ids) != len(set(component_ids)):
        fail("closure.excluded_no_edge_components contains duplicate components")
    if observed_components != EXPECTED_NO_EDGE_COMPONENTS:
        fail("closure excluded-component inventory or edge classes differ")
    overlap = prohibited_roles & required_role_ids
    if overlap:
        fail(
            "closure prohibited no-edge roles overlap required review roles: "
            f"{sorted(overlap)}"
        )

    closures = closure_source["decisions"]
    if not isinstance(closures, list) or len(closures) != len(EXPECTED_IDS):
        fail("closure.decisions must contain exactly ADR-001 through ADR-011")
    closure_ids: list[str] = []
    question_ids: list[str] = []
    document_anchors: list[str] = []
    b03_source_anchors: list[str] = []
    semantic_case_ids: list[str] = []
    generated_by_id = {decision["id"]: decision for decision in generated}
    anchor_content_cache: dict[str, str] = {}

    def anchor_source_text(source_path: str) -> str:
        if source_path not in anchor_content_cache:
            content = read_repository_regular_file(
                source_path,
                maximum_bytes=MAX_ADR_MARKDOWN_BYTES,
                label=f"semantic closure anchor source {source_path}",
            )
            try:
                anchor_content_cache[source_path] = content.decode("utf-8")
            except UnicodeDecodeError as error:
                fail(
                    f"semantic closure anchor source {source_path} is not UTF-8: "
                    f"{error}"
                )
        return anchor_content_cache[source_path]

    def validate_document_anchor(
        value: Any,
        *,
        path: str,
        allowed_sources: set[str],
        track_unique: bool = True,
    ) -> str:
        anchor = bounded_string(value, path, minimum=16, maximum=512)
        if anchor.count("#") != 1:
            fail(f"{path} must contain one repository path and heading fragment")
        source_path, fragment = anchor.split("#", 1)
        relative_path(source_path, f"{path} source path")
        if source_path not in allowed_sources:
            fail(f"{path} does not identify a bound ADR or module source")
        if not ROLE_ID.fullmatch(fragment):
            fail(f"{path} heading fragment is not canonical lowercase kebab case")
        source_text = anchor_source_text(source_path)

        def heading_fragment(heading: str) -> str:
            return re.sub(r"[^a-z0-9 -]", "", heading.casefold()).replace(" ", "-")

        matches = sum(
            heading_fragment(line[3:].strip()) == fragment
            for line in source_text.splitlines()
            if line.startswith("## ")
        )
        if matches != 1:
            fail(f"{path} does not resolve exactly one level-two heading")
        if track_unique:
            document_anchors.append(anchor)
        return anchor

    for index, closure in enumerate(closures):
        path = f"closure.decisions[{index}]"
        exact_keys(
            closure,
            {"id", "adr_source_set_sha256", "questions", "example_requirements"},
            path,
        )
        identifier = bounded_string(closure["id"], f"{path}.id", minimum=7, maximum=7)
        if identifier not in generated_by_id:
            fail(f"{path}.id is unknown")
        closure_ids.append(identifier)
        if (
            closure["adr_source_set_sha256"]
            != generated_by_id[identifier]["source_set"]["sha256"]
        ):
            fail(f"{path}.adr_source_set_sha256 is stale")
        required_roles = {
            requirement["role_id"]
            for requirement in generated_by_id[identifier]["required_reviews"]
        }
        allowed_sources = {
            source_identity["path"]
            for source_identity in generated_by_id[identifier]["source_set"]["sources"]
        }
        questions = closure["questions"]
        if (
            not isinstance(questions, list)
            or not 1 <= len(questions) <= 16
            or any(not isinstance(question, dict) for question in questions)
        ):
            fail(f"{path}.questions must contain 1..16 entries")
        if [
            (question.get("question_id"), question.get("question_anchor"))
            for question in questions
        ] != list(EXPECTED_QUESTION_ANCHORS[identifier]):
            fail(f"{path}.questions inventory, order, or anchors differ")
        for question_index, question in enumerate(questions):
            question_path = f"{path}.questions[{question_index}]"
            exact_keys(
                question,
                {
                    "question_id",
                    "question_anchor",
                    "statement",
                    "state",
                    "resolution",
                    "resolution_anchor",
                    "b03_deferral",
                },
                question_path,
            )
            question_id = bounded_string(
                question["question_id"],
                f"{question_path}.question_id",
                minimum=3,
                maximum=64,
            )
            if not CONDITION_ID.fullmatch(question_id) or not question_id.startswith(
                f"{identifier}-Q"
            ):
                fail(f"{question_path}.question_id is not bound to {identifier}")
            question_ids.append(question_id)
            question_anchor = validate_document_anchor(
                question["question_anchor"],
                path=f"{question_path}.question_anchor",
                allowed_sources=allowed_sources,
            )
            bounded_string(
                question["statement"],
                f"{question_path}.statement",
                minimum=10,
                maximum=1024,
            )
            state = question["state"]
            if state == "OPEN":
                if (
                    question["resolution"] is not None
                    or question["resolution_anchor"] is not None
                    or question["b03_deferral"] is not None
                ):
                    fail(f"{question_path} OPEN state cannot claim resolution")
                continue
            if state == "CLOSED":
                bounded_string(
                    question["resolution"],
                    f"{question_path}.resolution",
                    minimum=10,
                    maximum=1024,
                )
                resolution_anchor = validate_document_anchor(
                    question["resolution_anchor"],
                    path=f"{question_path}.resolution_anchor",
                    allowed_sources=allowed_sources,
                )
                if resolution_anchor == question_anchor:
                    fail(f"{question_path} reuses its question anchor as resolution")
                if question["b03_deferral"] is not None:
                    fail(f"{question_path} CLOSED state cannot defer to B03")
                continue
            if (
                state != "DEFERRED_B03"
                or question["resolution"] is not None
                or question["resolution_anchor"] is not None
            ):
                fail(f"{question_path}.state is invalid")
            deferral = question["b03_deferral"]
            if not isinstance(deferral, dict):
                fail(f"{question_path}.b03_deferral must be an object")
            exact_keys(
                deferral,
                {
                    "owner_task",
                    "owner_role_id",
                    "parameters",
                    "identity_eligibility_universes",
                    "identity_eligibility_required",
                    "equality_at_minimum",
                    "equality_at_maximum",
                    "below_minimum",
                    "above_maximum",
                    "arithmetic_overflow",
                    "permissive_default",
                    "failure_behavior",
                    "meaning_change",
                    "source_anchor",
                    "validation_state",
                },
                f"{question_path}.b03_deferral",
            )
            if deferral["owner_task"] != "B03":
                fail(f"{question_path}.b03_deferral.owner_task must be B03")
            expected_binding = EXPECTED_B03_BINDINGS.get(question_id)
            if (
                expected_binding is None
                or deferral["owner_role_id"] != expected_binding[0]
            ):
                fail(f"{question_path}.b03_deferral binding is not exact")
            if deferral["owner_role_id"] not in required_roles:
                fail(
                    f"{question_path}.b03_deferral.owner_role_id is not a "
                    f"required {identifier} review role"
                )
            if (
                deferral["equality_at_minimum"] != "PASS"
                or deferral["equality_at_maximum"] != "PASS"
                or deferral["below_minimum"] != "REJECT_BEFORE_ALLOCATION"
                or deferral["above_maximum"] != "REJECT_BEFORE_ALLOCATION"
                or deferral["arithmetic_overflow"] != "REJECT_BEFORE_ALLOCATION"
                or deferral["permissive_default"] is not False
                or deferral["failure_behavior"] != "REJECT_BEFORE_ALLOCATION"
                or deferral["meaning_change"] != "FORBIDDEN"
            ):
                fail(f"{question_path}.b03_deferral weakens bounded failure semantics")
            if (
                deferral["source_anchor"]
                != f"ncp-b01-selector-allocation-{identifier.lower()}-v1"
            ):
                fail(f"{question_path}.b03_deferral.source_anchor is stale")
            b03_source_anchors.append(deferral["source_anchor"])
            html_anchor = f'<a id="{deferral["source_anchor"]}"></a>'
            if (
                sum(
                    anchor_source_text(source_path).count(html_anchor)
                    for source_path in allowed_sources
                )
                != 1
            ):
                fail(
                    f"{question_path}.b03_deferral.source_anchor does not resolve "
                    "exactly one bound source anchor"
                )
            validation_state = bounded_string(
                deferral["validation_state"],
                f"{question_path}.b03_deferral.validation_state",
                minimum=4,
                maximum=9,
            )
            if validation_state not in {"OPEN", "VALIDATED"}:
                fail(f"{question_path}.b03_deferral.validation_state is invalid")
            parameters = deferral["parameters"]
            if (
                not isinstance(parameters, list)
                or [
                    (parameter.get("parameter_id"), parameter.get("value_kind"))
                    for parameter in parameters
                    if isinstance(parameter, dict)
                ]
                != list(expected_binding[1])
                or len(parameters) != len(expected_binding[1])
            ):
                fail(f"{question_path}.b03_deferral parameter inventory differs")
            expected_eligibility_parameter_ids = [
                parameter_id
                for parameter_id, value_kind in expected_binding[1]
                if value_kind == "EXACT_IDENTITY_SET"
            ]
            eligibility_universes = deferral["identity_eligibility_universes"]
            if deferral["identity_eligibility_required"] is not bool(
                expected_eligibility_parameter_ids
            ):
                fail(
                    f"{question_path}.b03_deferral identity eligibility requirement "
                    "differs from its parameter kinds"
                )
            if (
                not isinstance(eligibility_universes, list)
                or any(
                    not isinstance(universe, dict) for universe in eligibility_universes
                )
                or [universe.get("parameter_id") for universe in eligibility_universes]
                != expected_eligibility_parameter_ids
            ):
                fail(
                    f"{question_path}.b03_deferral identity eligibility inventory "
                    "differs"
                )
            eligibility_by_parameter: dict[str, list[str]] = {}
            for universe_index, universe in enumerate(eligibility_universes):
                universe_path = (
                    f"{question_path}.b03_deferral.identity_eligibility_universes["
                    f"{universe_index}]"
                )
                exact_keys(
                    universe,
                    {
                        "parameter_id",
                        "eligible_identities",
                        "eligible_identities_sha256",
                    },
                    universe_path,
                )
                parameter_id = bounded_string(
                    universe["parameter_id"],
                    f"{universe_path}.parameter_id",
                    minimum=2,
                    maximum=64,
                )
                eligible_identities = universe["eligible_identities"]
                if (
                    not isinstance(eligible_identities, list)
                    or len(eligible_identities) > 4096
                    or any(
                        not isinstance(value, str)
                        or not 1 <= len(value.encode("utf-8")) <= 256
                        or any(
                            not 0x21 <= ord(character) <= 0x7E for character in value
                        )
                        for value in eligible_identities
                    )
                    or eligible_identities
                    != sorted(
                        set(eligible_identities),
                        key=lambda value: value.encode("utf-8"),
                    )
                ):
                    fail(f"{universe_path}.eligible_identities is not canonical")
                if any(
                    "cortexel"
                    in {
                        token
                        for token in re.split(r"[^a-z0-9]+", value.lower())
                        if token
                    }
                    for value in eligible_identities
                ):
                    fail(
                        f"{universe_path}.eligible_identities violates the global "
                        "Cortexel no-edge exclusion"
                    )
                observed_digest = universe["eligible_identities_sha256"]
                if validation_state == "OPEN":
                    if eligible_identities or observed_digest is not None:
                        fail(
                            f"{universe_path} OPEN state must expose an unbound "
                            "eligibility universe"
                        )
                elif eligible_identities:
                    if observed_digest != b03_eligibility_set_sha256(
                        question_id,
                        parameter_id,
                        eligible_identities,
                    ):
                        fail(
                            f"{universe_path} does not bind its exact eligibility "
                            "universe and context digest"
                        )
                elif observed_digest is not None:
                    fail(
                        f"{universe_path} source-predicate eligibility cannot carry "
                        "an exact-universe digest"
                    )
                eligibility_by_parameter[parameter_id] = eligible_identities
            for parameter_index, parameter in enumerate(parameters, start=1):
                parameter_path = (
                    f"{question_path}.b03_deferral.parameters[{parameter_index - 1}]"
                )
                exact_keys(
                    parameter,
                    {
                        "parameter_id",
                        "value_kind",
                        "selection_predicate_id",
                        "selection_predicate_source_anchor",
                        "selection_profile",
                        "b03_selection_verifier_required",
                        "inherits_excluded_no_edge_components",
                        "minimum",
                        "maximum",
                        "required_tests",
                    },
                    parameter_path,
                )
                parameter_id = bounded_string(
                    parameter["parameter_id"],
                    f"{parameter_path}.parameter_id",
                    minimum=2,
                    maximum=64,
                )
                if not CONDITION_ID.fullmatch(parameter_id):
                    fail(f"{parameter_path}.parameter_id is not canonical")
                tests = parameter["required_tests"]
                expected_tests = [
                    f"{identifier}-B03-P{parameter_index:02}-{suffix}"
                    for suffix in B03_TEST_SUFFIXES_BY_KIND[parameter["value_kind"]]
                ]
                if tests != expected_tests:
                    fail(f"{parameter_path}.required_tests is invalid")
                expected_predicate_id = (
                    f"{question_id}-P{parameter_index:02}-SELECTION-PREDICATE"
                )
                if parameter["selection_predicate_id"] != expected_predicate_id:
                    fail(f"{parameter_path}.selection_predicate_id is not exact")
                if (
                    parameter["selection_predicate_source_anchor"]
                    != deferral["source_anchor"]
                ):
                    fail(
                        f"{parameter_path}.selection_predicate_source_anchor is not "
                        "bound to its accepted deferral source"
                    )
                if parameter["selection_profile"] != (
                    f"B03_{parameter['value_kind']}_SELECTION_V1"
                ):
                    fail(f"{parameter_path}.selection_profile is not exact")
                if parameter["b03_selection_verifier_required"] is not True:
                    fail(
                        f"{parameter_path}.b03_selection_verifier_required must be true"
                    )
                if parameter["inherits_excluded_no_edge_components"] is not True:
                    fail(
                        f"{parameter_path}.inherits_excluded_no_edge_components "
                        "must be true"
                    )
                minimum = parameter["minimum"]
                maximum = parameter["maximum"]
                if validation_state == "OPEN":
                    if minimum is not None or maximum is not None:
                        fail(
                            f"{parameter_path} OPEN state must expose missing "
                            "deferral-envelope bounds"
                        )
                    continue
                value_kind = parameter["value_kind"]
                lower_bound = (
                    0
                    if value_kind == "EXACT_IDENTITY_SET"
                    or (question_id, parameter_id)
                    in ZERO_MINIMUM_BOUNDED_INTEGER_PARAMETERS
                    else 1
                )
                bounded_integer(
                    minimum,
                    f"{parameter_path}.minimum",
                    minimum=lower_bound,
                    maximum=MAX_B03_LITERAL_INTEGER,
                )
                bounded_integer(
                    maximum,
                    f"{parameter_path}.maximum",
                    minimum=lower_bound,
                    maximum=MAX_B03_LITERAL_INTEGER,
                )
                if minimum > maximum:
                    fail(f"{parameter_path} has inverted bounds")
                if (
                    value_kind == "EXACT_IDENTITY_SET"
                    and eligibility_by_parameter[parameter_id]
                    and maximum > len(eligibility_by_parameter[parameter_id])
                ):
                    fail(
                        f"{parameter_path} envelope exceeds its exact B01-bound "
                        "eligibility universe"
                    )
                if parameter["value_kind"] not in {
                    "BOUNDED_INTEGER",
                    "EXACT_IDENTITY_SET",
                }:
                    fail(f"{parameter_path}.value_kind is invalid")

        examples = closure["example_requirements"]
        exact_keys(
            examples,
            {
                "corpus_path",
                "required_corpus_status",
                "required_source_paths",
                "required_case_ids",
            },
            f"{path}.example_requirements",
        )
        if (
            examples["corpus_path"] != SEMANTIC_CORPUS_PATH
            or examples["required_corpus_status"] != "COMPLETE_CURRENT"
        ):
            fail(f"{path}.example_requirements does not require the current corpus")
        expected_source_paths = [
            source_identity["path"]
            for source_identity in generated_by_id[identifier]["source_set"]["sources"]
        ]
        if examples["required_source_paths"] != expected_source_paths:
            fail(f"{path}.example_requirements omits or reorders an ADR source")
        required_case_ids = examples["required_case_ids"]
        if (
            not isinstance(required_case_ids, list)
            or not 1 <= len(required_case_ids) <= 16
        ):
            fail(f"{path}.example_requirements must contain 1..16 case IDs")
        for case_index, case_id in enumerate(required_case_ids):
            case_path = f"{path}.example_requirements.required_case_ids[{case_index}]"
            if (
                not isinstance(case_id, str)
                or not SEMANTIC_CASE_ID.fullmatch(case_id)
                or len(case_id.encode("utf-8")) > 160
                or not case_id.startswith(identifier.lower().replace("-", "") + ".")
            ):
                fail(f"{case_path}.case_id is invalid")
            semantic_case_ids.append(case_id)
        if len(required_case_ids) != len(set(required_case_ids)):
            fail(f"{path}.example_requirements contains duplicate case IDs")

    if tuple(closure_ids) != EXPECTED_IDS:
        fail("closure.decisions IDs are missing or out of order")
    if len(question_ids) != len(set(question_ids)):
        fail("closure.decisions contains duplicate question IDs")
    if len(document_anchors) != len(set(document_anchors)):
        fail("closure.decisions reuses a question or resolution anchor")
    if len(b03_source_anchors) != len(set(b03_source_anchors)):
        fail("closure.decisions reuses a B03 source anchor")
    if len(semantic_case_ids) != len(set(semantic_case_ids)):
        fail("closure.decisions contains duplicate required semantic-case IDs")

    return {
        "source": closure_source,
        "source_content": closure_source_content,
        "schema_content": closure_schema_content,
        "binding": {
            "source": repository_file_identity(
                CLOSURE_SOURCE,
                content_override=closure_source_content,
            ),
            "json_schema": repository_file_identity(
                CLOSURE_SCHEMA,
                content_override=closure_schema_content,
            ),
        },
        "by_id": {closure["id"]: closure for closure in closures},
    }


def read_closure_artifact(
    repository_path: str,
    *,
    artifact_overrides: dict[str, bytes] | None,
    referenced_overrides: set[str],
    maximum_bytes: int = MAX_JSON_BYTES,
) -> tuple[dict[str, Any], bytes] | None:
    relative = relative_path(repository_path, "semantic closure artifact path")
    if artifact_overrides is not None and relative in artifact_overrides:
        content = artifact_overrides[relative]
        referenced_overrides.add(relative)
        if type(content) is not bytes or not 1 <= len(content) <= maximum_bytes:
            fail(
                f"semantic closure artifact override {relative} must contain "
                f"1..{maximum_bytes} native bytes"
            )
    else:
        try:
            (ROOT / relative).lstat()
        except FileNotFoundError:
            return None
        except OSError as error:
            fail(f"cannot inspect semantic closure artifact {relative}: {error}")
        content = read_repository_regular_file(
            relative,
            maximum_bytes=maximum_bytes,
            label=f"semantic closure artifact {relative}",
        )
    return (
        {
            "path": relative,
            "sha256": sha256_bytes(content),
            "bytes": len(content),
        },
        content,
    )


def expected_corpus_decision_binding(
    current_set: dict[str, Any], projection_payload: bytes
) -> dict[str, Any]:
    return {
        "schema": DECISION_SET_SCHEMA,
        "registry_path": OUTPUT.relative_to(ROOT).as_posix(),
        "digest_algorithm": ("sha256(domain || u64be(projection_bytes) || projection)"),
        "domain_hex": DECISION_SET_DOMAIN.hex(),
        "projection_encoding": "UTF8_JSON_SORTED_KEYS_COMPACT_ENSURE_ASCII_FALSE",
        "projection_members": list(DECISION_SET_PROJECTION_MEMBERS),
        "decision_members": list(DECISION_PROJECTION_MEMBERS),
        "projection_byte_length": len(projection_payload),
        "projection_sha256": sha256_bytes(projection_payload),
        "sha256": current_set["sha256"],
        "semantic_closure": copy.deepcopy(current_set["semantic_closure"]),
        "effect": "NON_ACCEPTING_EXACT_SUBJECT_BINDING_ONLY",
    }


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def bound_semantic_object(
    case: dict[str, Any],
    requirement: dict[str, Any],
    *,
    case_path: str,
) -> dict[str, Any] | None:
    source_value = case.get("source")
    if not isinstance(source_value, dict):
        return None
    if set(source_value) != {
        "adr",
        "json_fence_ordinal",
        "fence_byte_length",
        "fence_sha256",
    }:
        return None
    source_identity = requirement["source_identity"]
    ordinal = source_value.get("json_fence_ordinal")
    if (
        source_value.get("adr") != requirement["decision_id"]
        or type(ordinal) is not int
        or not 1 <= ordinal <= 64
    ):
        return None
    content = read_repository_regular_file(
        source_identity["path"],
        maximum_bytes=MAX_ADR_MARKDOWN_BYTES,
        label=f"{case_path} bound ADR source",
    )
    if (
        len(content) != source_identity["bytes"]
        or sha256_bytes(content) != source_identity["sha256"]
    ):
        return None
    try:
        fences = extract_exact_json_fences(
            content.decode("utf-8"), label=f"{case_path} bound ADR source"
        )
    except UnicodeDecodeError:
        return None
    if ordinal > len(fences):
        return None
    fence_content = fences[ordinal - 1].encode("utf-8")
    if source_value.get("fence_byte_length") != len(fence_content) or source_value.get(
        "fence_sha256"
    ) != sha256_bytes(fence_content):
        return None
    try:
        wire_object = parse_json_fence(
            fences[ordinal - 1],
            label=f"{case_path} bound ADR JSON fence",
            limits=ADR_FENCE_JSON_LIMITS,
        )
    except RegistryError:
        return None
    return wire_object if isinstance(wire_object, dict) else None


def apply_single_semantic_mutation(
    positive: dict[str, Any], mutation: Any
) -> dict[str, Any] | None:
    if not isinstance(mutation, dict):
        return None
    operation = mutation.get("op")
    if not isinstance(operation, str):
        return None
    required_keys = {"target", "op", "path"}
    if operation in {"ADD", "REPLACE"}:
        required_keys.add("value")
    target = mutation.get("target")
    if not isinstance(target, str):
        return None
    if set(mutation) != required_keys or target not in {
        "DOCUMENT",
        "BOUNDED_FIXTURE",
    }:
        return None
    if operation not in {"ADD", "REMOVE", "REPLACE"}:
        return None
    if operation in {"ADD", "REPLACE"}:
        try:
            validate_native_json_tree(
                mutation.get("value"),
                limits=SEMANTIC_OBJECT_JSON_LIMITS,
                label="semantic corpus patch value",
            )
        except BoundedJsonError:
            return None
    path = mutation.get("path")
    if (
        not isinstance(path, str)
        or not 1 <= len(path.encode("utf-8")) <= 512
        or not path.startswith("/")
    ):
        return None

    def decode_pointer_segment(segment: str) -> str | None:
        decoded: list[str] = []
        index = 0
        while index < len(segment):
            if segment[index] != "~":
                decoded.append(segment[index])
                index += 1
                continue
            if index + 1 >= len(segment) or segment[index + 1] not in {"0", "1"}:
                return None
            decoded.append("~" if segment[index + 1] == "0" else "/")
            index += 2
        return "".join(decoded)

    def array_index(segment: str) -> int | None:
        if (
            not segment
            or (len(segment) > 1 and segment.startswith("0"))
            or not segment.isascii()
            or not segment.isdigit()
        ):
            return None
        return int(segment)

    segments: list[str] = []
    for encoded in path[1:].split("/"):
        decoded = decode_pointer_segment(encoded)
        if decoded is None:
            return None
        segments.append(decoded)
    if not segments:
        return None
    mutated: Any = copy.deepcopy(positive)
    parent: Any = mutated
    for segment in segments[:-1]:
        if isinstance(parent, dict) and segment in parent:
            parent = parent[segment]
        elif isinstance(parent, list):
            offset = array_index(segment)
            if offset is None or offset >= len(parent):
                return None
            parent = parent[offset]
        else:
            return None
    leaf = segments[-1]
    if isinstance(parent, dict):
        exists = leaf in parent
        if operation == "ADD" and exists:
            return None
        if operation in {"REMOVE", "REPLACE"} and not exists:
            return None
        if operation == "REMOVE":
            del parent[leaf]
        else:
            parent[leaf] = copy.deepcopy(mutation["value"])
    elif isinstance(parent, list):
        if operation == "ADD" and leaf == "-":
            parent.append(copy.deepcopy(mutation["value"]))
            offset = None
        else:
            offset = array_index(leaf)
            if offset is None:
                return None
        if operation == "ADD":
            if offset is not None and offset > len(parent):
                return None
            if offset is not None:
                parent.insert(offset, copy.deepcopy(mutation["value"]))
        elif offset is None or offset >= len(parent):
            return None
        elif operation == "REMOVE":
            parent.pop(offset)
        else:
            parent[offset] = copy.deepcopy(mutation["value"])
    else:
        return None
    if not isinstance(mutated, dict):
        return None
    try:
        validate_native_json_tree(
            mutated,
            limits=SEMANTIC_OBJECT_JSON_LIMITS,
            label="mutated semantic corpus object",
        )
    except BoundedJsonError:
        return None
    if mutated == positive:
        return None
    return mutated


def validate_semantic_corpus(
    content: bytes,
    identity: dict[str, Any],
    *,
    current_set: dict[str, Any],
    projection_payload: bytes,
    required_cases: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, bool], int, int]:
    if set(required_cases) != set(EXPECTED_SEMANTIC_CASE_IDENTITIES):
        fail("semantic closure case requirements differ from the closed v1 inventory")
    try:
        corpus = parse_json_bytes(
            content,
            limits=SEMANTIC_CORPUS_JSON_LIMITS,
            label=identity["path"],
        )
    except BoundedJsonError as error:
        fail(f"cannot parse {identity['path']}: {error}")
    if not isinstance(corpus, dict):
        fail(f"{identity['path']} must contain one JSON object")
    if set(corpus) != {
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
    }:
        fail("semantic closure corpus top-level shape differs")
    if corpus.get("schema") != SEMANTIC_CORPUS_SCHEMA:
        fail("semantic closure corpus has an unknown schema")
    if (
        corpus.get("schema_version") != 1
        or corpus.get("task") != "B01"
        or corpus.get("candidate") != "1.0.0-rc.1"
        or corpus.get("wire_version") != "1.0"
    ):
        fail("semantic closure corpus identity fields differ")
    if len(content) > EXPECTED_SEMANTIC_LIMITS["maximum_corpus_bytes"]:
        fail("semantic closure corpus exceeds its closed v1 byte bound")
    if corpus.get("source_binding") != EXPECTED_SEMANTIC_SOURCE_BINDING:
        fail("semantic closure corpus source binding differs from v1")
    if corpus.get("limits") != EXPECTED_SEMANTIC_LIMITS:
        fail("semantic closure corpus limits differ from v1")
    if corpus.get("closed_values") != EXPECTED_SEMANTIC_CLOSED_VALUES:
        fail("semantic closure corpus closed values differ from v1")
    diagnostic_registry = corpus.get("diagnostic_registry")
    if (
        not isinstance(diagnostic_registry, list)
        or not 1 <= len(diagnostic_registry) <= 256
        or any(
            not isinstance(diagnostic, str)
            or CONDITION_ID.fullmatch(diagnostic) is None
            for diagnostic in diagnostic_registry
        )
        or diagnostic_registry != sorted(set(diagnostic_registry))
    ):
        fail("semantic closure corpus diagnostics are not a closed vocabulary")
    diagnostic_set = set(diagnostic_registry)
    boundary = corpus.get("claim_boundary")
    expected_boundary_keys = {
        "adrs_accepted",
        "normative_contract_changed",
        "production_admission_implemented",
        "interoperability_established",
        "independent_evidence_satisfied",
        "external_gate_satisfied",
        "release_authorized",
    }
    if (
        not isinstance(boundary, dict)
        or set(boundary) != expected_boundary_keys
        or any(value is not False for value in boundary.values())
    ):
        fail("semantic closure corpus overclaims its authority boundary")
    cases = corpus.get("cases")
    if (
        not isinstance(cases, list)
        or len(cases) != EXPECTED_SEMANTIC_LIMITS["expected_case_count"]
    ):
        fail("semantic closure corpus case count differs from v1")
    by_id: dict[str, dict[str, Any]] = {}
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            fail(f"semantic closure corpus case {index} must be an object")
        case_id = bounded_string(
            case.get("id"), f"semantic closure corpus case {index}.id", maximum=128
        )
        if case_id in by_id:
            fail(f"semantic closure corpus duplicates case ID {case_id}")
        by_id[case_id] = case
    if set(by_id) != set(required_cases):
        fail("semantic closure corpus case inventory differs from its requirements")
    if list(by_id) != list(required_cases):
        fail("semantic closure corpus case order differs from its requirements")
    satisfied: dict[str, bool] = {}
    positive_by_decision = {identifier: False for identifier in EXPECTED_IDS}
    rejection_by_decision = {identifier: False for identifier in EXPECTED_IDS}
    mutation_ids: set[str] = set()
    used_diagnostics: set[str] = set()
    mutation_count = 0
    aggregate_adr_bytes = 0
    observed_adr_identities: dict[str, tuple[int, str]] = {}
    observed_source_coordinates: set[tuple[str, int]] = set()
    previous_source_coordinate: tuple[str, int] | None = None
    for case_id, requirement in required_cases.items():
        case = by_id.get(case_id)
        if not isinstance(case, dict):
            satisfied[case_id] = False
            continue
        expected_keys = {
            "id",
            "source",
            "scope",
            "profile",
            "polarity",
            "expected_profile_result",
            "production_admission",
            "expected_diagnostics",
            "payload_interpreted",
            "bounded_fixture",
            "mutations",
        }
        diagnostics = case.get("expected_diagnostics")
        source = case.get("source")
        source_adr = source.get("adr") if isinstance(source, dict) else None
        source_identity = requirement["source_identity"]
        source_path = (
            source_identity["path"]
            if source_adr == requirement["decision_id"]
            else None
        )
        polarity = case.get("polarity")
        expected_result = case.get("expected_profile_result")
        admission = case.get("production_admission")
        is_positive = (
            polarity == "POSITIVE"
            and isinstance(expected_result, str)
            and expected_result
            in {"MATCH_NON_AUTHORIZING_EXCERPT", "MATCH_NON_WIRE_EXCERPT"}
            and isinstance(admission, str)
            and admission in {"NOT_APPLICABLE", "NOT_EVALUATED", "REJECT"}
            and diagnostics == []
        )
        is_negative = (
            polarity == "NEGATIVE"
            and expected_result == "REJECT"
            and admission == "REJECT"
            and isinstance(diagnostics, list)
            and bool(diagnostics)
        )
        source_ordinal = (
            source.get("json_fence_ordinal") if isinstance(source, dict) else None
        )
        expected_identity = EXPECTED_SEMANTIC_CASE_IDENTITIES.get(case_id)
        identity_matches = (
            expected_identity is not None
            and (
                case.get("profile"),
                case.get("scope"),
                polarity,
                source_adr,
                source_ordinal,
            )
            == expected_identity
        )
        source_coordinate = (
            (source_path, source_ordinal)
            if isinstance(source_path, str) and type(source_ordinal) is int
            else None
        )
        common = (
            set(case) == expected_keys
            and case.get("id") == case_id
            and identity_matches
            and isinstance(case.get("scope"), str)
            and case.get("scope") in EXPECTED_SEMANTIC_CLOSED_VALUES["scope"]
            and isinstance(case.get("profile"), str)
            and SEMANTIC_PROFILE_ID.fullmatch(case["profile"]) is not None
            and case["profile"].startswith(
                requirement["decision_id"].replace("-", "") + "_"
            )
            and (is_positive or is_negative)
            and type(case.get("payload_interpreted")) is bool
            and (not is_positive or case.get("payload_interpreted") is True)
            and isinstance(case.get("bounded_fixture"), dict)
            and len(canonical_json_bytes(case["bounded_fixture"]))
            <= EXPECTED_SEMANTIC_LIMITS["maximum_fixture_bytes"]
            and isinstance(diagnostics, list)
            and len(diagnostics) <= 32
            and all(
                isinstance(diagnostic, str) and diagnostic in diagnostic_set
                for diagnostic in diagnostics
            )
            and diagnostics == sorted(set(diagnostics))
            and source_identity is not None
            and source_coordinate is not None
            and (
                previous_source_coordinate is None
                or previous_source_coordinate < source_coordinate
            )
            and (
                (case.get("scope") == "NON_WIRE_INTERNAL_STATE")
                == (expected_result == "MATCH_NON_WIRE_EXCERPT")
            )
        )
        if source_coordinate is not None:
            previous_source_coordinate = source_coordinate
            observed_source_coordinates.add(source_coordinate)
        if isinstance(source_path, str):
            adr_bytes = source_identity["bytes"]
            adr_digest = source_identity["sha256"]
            prior = observed_adr_identities.get(source_path)
            if prior is not None and prior != (adr_bytes, adr_digest):
                common = False
            elif prior is None:
                observed_adr_identities[source_path] = (adr_bytes, adr_digest)
                aggregate_adr_bytes += adr_bytes
        if isinstance(diagnostics, list):
            used_diagnostics.update(
                diagnostic for diagnostic in diagnostics if isinstance(diagnostic, str)
            )
        bound_object = (
            bound_semantic_object(
                case,
                {
                    "decision_id": requirement["decision_id"],
                    "source_identity": source_identity,
                },
                case_path=f"semantic closure corpus case {case_id}",
            )
            if source_path is not None
            else None
        )
        mutations = case.get("mutations")
        mutation_rejection = False
        if (
            not isinstance(mutations, list)
            or not EXPECTED_SEMANTIC_LIMITS["minimum_mutations_per_case"]
            <= len(mutations)
            <= EXPECTED_SEMANTIC_LIMITS["maximum_mutations_per_case"]
        ):
            common = False
            mutations = []
        for mutation_index, mutation in enumerate(mutations):
            mutation_path = (
                f"semantic closure corpus case {case_id} mutation {mutation_index}"
            )
            if not isinstance(mutation, dict) or set(mutation) != {
                "id",
                "purpose",
                "patch",
                "expected_profile_result",
                "production_admission",
                "expected_diagnostics",
                "payload_interpreted",
            }:
                common = False
                continue
            mutation_id = mutation.get("id")
            mutation_diagnostics = mutation.get("expected_diagnostics")
            patch_target = (
                mutation.get("patch", {}).get("target")
                if isinstance(mutation.get("patch"), dict)
                else None
            )
            patch_subject = (
                bound_object
                if patch_target == "DOCUMENT"
                else case.get("bounded_fixture")
                if patch_target == "BOUNDED_FIXTURE"
                else None
            )
            applied_mutation = (
                apply_single_semantic_mutation(patch_subject, mutation.get("patch"))
                if isinstance(patch_subject, dict)
                else None
            )
            applied_bound = (
                EXPECTED_SEMANTIC_LIMITS["maximum_fixture_bytes"]
                if patch_target == "BOUNDED_FIXTURE"
                else EXPECTED_SEMANTIC_LIMITS["maximum_json_fence_bytes"]
            )
            applied_tree_valid = False
            if applied_mutation is not None:
                try:
                    validate_native_json_tree(
                        applied_mutation,
                        limits=SEMANTIC_OBJECT_JSON_LIMITS,
                        label=f"{mutation_path} applied value",
                    )
                except BoundedJsonError:
                    pass
                else:
                    applied_tree_valid = True
            mutation_valid = (
                isinstance(mutation_id, str)
                and SEMANTIC_CASE_ID.fullmatch(mutation_id) is not None
                and len(mutation_id.encode("utf-8")) <= 160
                and mutation_id.startswith(
                    requirement["decision_id"].lower().replace("-", "") + "."
                )
                and mutation_id not in mutation_ids
                and mutation_id not in by_id
                and isinstance(mutation.get("purpose"), str)
                and bool(mutation["purpose"].strip())
                and 1 <= len(mutation["purpose"].encode("utf-8")) <= 512
                and isinstance(mutation.get("patch"), dict)
                and mutation.get("expected_profile_result") == "REJECT"
                and isinstance(mutation.get("production_admission"), str)
                and mutation.get("production_admission") in {"NOT_APPLICABLE", "REJECT"}
                and isinstance(mutation_diagnostics, list)
                and 1 <= len(mutation_diagnostics) <= 32
                and all(
                    isinstance(diagnostic, str) and diagnostic in diagnostic_set
                    for diagnostic in mutation_diagnostics
                )
                and mutation_diagnostics == sorted(set(mutation_diagnostics))
                and type(mutation.get("payload_interpreted")) is bool
                and applied_mutation is not None
                and applied_tree_valid
                and len(canonical_json_bytes(applied_mutation)) <= applied_bound
                and (
                    mutation.get("expected_profile_result") != expected_result
                    or mutation.get("production_admission") != admission
                    or mutation_diagnostics != diagnostics
                    or mutation.get("payload_interpreted")
                    != case.get("payload_interpreted")
                )
            )
            if not mutation_valid:
                common = False
                continue
            mutation_ids.add(mutation_id)
            mutation_rejection = True
            used_diagnostics.update(
                diagnostic
                for diagnostic in mutation_diagnostics
                if isinstance(diagnostic, str)
            )
            bounded_string(
                mutation_id,
                f"{mutation_path}.id",
                minimum=8,
                maximum=128,
            )
        mutation_count += len(mutations)
        common = common and bound_object is not None and mutation_rejection
        satisfied[case_id] = common
        if common:
            decision_id = requirement["decision_id"]
            positive_by_decision[decision_id] |= is_positive
            rejection_by_decision[decision_id] |= is_negative or mutation_rejection
    coverage_complete = all(positive_by_decision.values()) and all(
        rejection_by_decision.values()
    )
    expected_source_coordinates: set[tuple[str, int]] = set()
    for source_path, (source_bytes, source_digest) in observed_adr_identities.items():
        content = read_repository_regular_file(
            source_path,
            maximum_bytes=MAX_ADR_MARKDOWN_BYTES,
            label=f"semantic closure ADR source {source_path}",
        )
        if len(content) != source_bytes or sha256_bytes(content) != source_digest:
            coverage_complete = False
            continue
        try:
            fences = extract_exact_json_fences(
                content.decode("utf-8"),
                label=f"semantic closure ADR source {source_path}",
            )
        except UnicodeDecodeError:
            coverage_complete = False
            continue
        expected_source_coordinates.update(
            (source_path, ordinal) for ordinal in range(1, len(fences) + 1)
        )
    coverage_complete = (
        coverage_complete and observed_source_coordinates == expected_source_coordinates
    )
    diagnostic_payload = canonical_json_bytes(diagnostic_registry)
    diagnostic_vocabulary_current = (
        len(diagnostic_registry) == EXPECTED_DIAGNOSTIC_REGISTRY_COUNT
        and len(diagnostic_payload) == EXPECTED_DIAGNOSTIC_REGISTRY_BYTE_LENGTH
        and sha256_bytes(diagnostic_payload) == EXPECTED_DIAGNOSTIC_REGISTRY_SHA256
    )
    corpus_contract_complete = (
        mutation_count == EXPECTED_SEMANTIC_LIMITS["expected_mutation_count"]
        and aggregate_adr_bytes
        <= EXPECTED_SEMANTIC_LIMITS["maximum_aggregate_adr_bytes"]
        and used_diagnostics == diagnostic_set
        and diagnostic_vocabulary_current
    )
    binding_current = corpus.get("decision_set_binding") == (
        expected_corpus_decision_binding(current_set, projection_payload)
    )
    if not binding_current:
        return (
            "STALE_DECISION_SET",
            satisfied,
            len(cases),
            mutation_count,
        )
    if (
        not all(satisfied.values())
        or not coverage_complete
        or not corpus_contract_complete
    ):
        return (
            "INCOMPLETE_COVERAGE",
            satisfied,
            len(cases),
            mutation_count,
        )
    return (
        "COMPLETE_CURRENT",
        satisfied,
        len(cases),
        mutation_count,
    )


def evaluate_semantic_closure(
    requirements: dict[str, Any],
    generated: list[dict[str, Any]],
    source: dict[str, Any],
    current_policy: dict[str, Any],
    current_set: dict[str, Any],
    *,
    artifact_overrides: dict[str, bytes] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    referenced_overrides: set[str] = set()
    if artifact_overrides is not None:
        for path, content in artifact_overrides.items():
            relative_path(path, "semantic closure artifact override path")
            if type(content) is not bytes:
                fail(f"semantic closure artifact override {path} must be bytes")

    projection = decision_set_projection(
        generated,
        source,
        current_policy,
        requirements["binding"],
    )
    projection_payload = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    required_cases: dict[str, dict[str, Any]] = {}
    generated_by_id = {decision["id"]: decision for decision in generated}
    for closure in requirements["source"]["decisions"]:
        examples = closure["example_requirements"]
        source_identity = generated_by_id[closure["id"]]["source_set"]["sources"][0]
        for case_id in examples["required_case_ids"]:
            required_cases[case_id] = {
                "decision_id": closure["id"],
                "source_identity": source_identity,
            }
    corpus_observed = read_closure_artifact(
        SEMANTIC_CORPUS_PATH,
        artifact_overrides=artifact_overrides,
        referenced_overrides=referenced_overrides,
    )
    if corpus_observed is None:
        corpus_identity = None
        corpus_status = "MISSING"
        case_satisfaction = {case_id: False for case_id in required_cases}
        case_count = 0
        mutation_count = 0
    else:
        corpus_identity, corpus_content = corpus_observed
        (
            corpus_status,
            case_satisfaction,
            case_count,
            mutation_count,
        ) = validate_semantic_corpus(
            corpus_content,
            corpus_identity,
            current_set=current_set,
            projection_payload=projection_payload,
            required_cases=required_cases,
        )
    b03_satisfaction: dict[str, bool] = {}
    for closure in requirements["source"]["decisions"]:
        for question in closure["questions"]:
            if question["state"] != "DEFERRED_B03":
                continue
            deferral = question["b03_deferral"]
            if deferral["validation_state"] != "VALIDATED":
                b03_satisfaction[question["question_id"]] = False
                continue
            b03_satisfaction[question["question_id"]] = True
    if artifact_overrides is not None:
        unknown = set(artifact_overrides) - referenced_overrides
        if unknown:
            fail(f"unknown semantic closure artifact overrides: {sorted(unknown)}")

    public = {
        "schema": SEMANTIC_CLOSURE_EVALUATION_SCHEMA,
        "decision_set_sha256": current_set["sha256"],
        "state": "OPEN",
        "source": copy.deepcopy(requirements["binding"]["source"]),
        "json_schema": copy.deepcopy(requirements["binding"]["json_schema"]),
        "semantic_corpus": {
            "required_path": SEMANTIC_CORPUS_PATH,
            "required_status": "COMPLETE_CURRENT",
            "observed_status": corpus_status,
            "observed_identity": corpus_identity,
            "case_count": case_count,
            "mutation_count": mutation_count,
        },
        "b03_deferrals": {
            "required_question_count": len(b03_satisfaction),
            "validated_question_count": sum(b03_satisfaction.values()),
            "observed_status": (
                "COMPLETE_ENVELOPES_VERIFIED"
                if b03_satisfaction and all(b03_satisfaction.values())
                else "INCOMPLETE_FAIL_CLOSED"
            ),
        },
    }
    return public, {
        "case_satisfaction": case_satisfaction,
        "b03_satisfaction": b03_satisfaction,
    }


def semantic_closure_blockers(
    decision: dict[str, Any],
    closure: dict[str, Any],
    evaluation: dict[str, Any],
    observations: dict[str, Any],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for question in closure["questions"]:
        if question["state"] == "OPEN":
            blockers.append(
                {
                    "code": "SEMANTIC_QUESTION_OPEN",
                    "closure_id": question["question_id"],
                    "detail": "the architecture question has no closed resolution",
                }
            )
        elif question["state"] == "DEFERRED_B03" and (
            question["b03_deferral"]["validation_state"] != "VALIDATED"
            or not observations["b03_satisfaction"].get(question["question_id"], False)
        ):
            blockers.append(
                {
                    "code": "INVALID_B03_DEFERRAL",
                    "closure_id": question["question_id"],
                    "detail": (
                        "the B03 deferral lacks complete positive literal bounds, "
                        "a finite outer maximum, or exact envelope tests; unknown "
                        "allocation must reject and future B03 selection cannot "
                        "change the accepted meaning"
                    ),
                }
            )

    examples = closure["example_requirements"]
    if evaluation["semantic_corpus"]["observed_status"] != "COMPLETE_CURRENT":
        blockers.append(
            {
                "code": "SEMANTIC_EXAMPLE_CORPUS_NOT_CURRENT",
                "closure_id": f"{decision['id']}-SEMANTIC-CORPUS",
                "detail": (
                    "the source-bound semantic corpus is missing, stale, or "
                    "does not cover every required case and rejection observation"
                ),
            }
        )
    case_satisfaction = observations["case_satisfaction"]
    for index, case_id in enumerate(examples["required_case_ids"], start=1):
        if not case_satisfaction[case_id]:
            blockers.append(
                {
                    "code": "SEMANTIC_EXAMPLE_MISSING",
                    "closure_id": f"{decision['id']}-SEMANTIC-CASE-{index}",
                    "detail": (
                        "the required source-bound semantic case is absent or "
                        f"invalid: {case_id}"
                    ),
                }
            )
    return blockers


def git_environment() -> dict[str, str]:
    environment = os.environ.copy()
    exact = {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_SYSTEM",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_REPLACE_REF_BASE",
        "GIT_WORK_TREE",
    }
    for key in list(environment):
        if key in exact or key.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")):
            environment.pop(key, None)
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_OPTIONAL_LOCKS": "0",
        }
    )
    return environment


def run_git(arguments: list[str], description: str) -> bytes:
    if GIT is None:
        fail("cannot resolve review subjects because git is unavailable")
    try:
        result = subprocess.run(  # noqa: S603
            [GIT, "--no-replace-objects", *arguments],
            cwd=ROOT,
            env=git_environment(),
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        fail(f"cannot resolve {description}: {error}")
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        fail(f"cannot resolve {description}: {detail or 'git command failed'}")
    return result.stdout


@lru_cache(maxsize=512)
def resolve_git_subject(source_commit: str, repository_path: str) -> tuple[str, bytes]:
    relative = relative_path(repository_path, "review subject repository path")
    object_type = (
        run_git(
            ["cat-file", "-t", source_commit],
            f"review source commit {source_commit}",
        )
        .decode("ascii", errors="strict")
        .strip()
    )
    if object_type != "commit":
        fail(f"review source object {source_commit} is not a Git commit")
    tree = (
        run_git(
            ["rev-parse", "--verify", f"{source_commit}^{{tree}}"],
            f"tree for review source commit {source_commit}",
        )
        .decode("ascii", errors="strict")
        .strip()
    )
    if not HEX40.fullmatch(tree):
        fail(f"review source commit {source_commit} resolved an invalid tree")
    tree_entry = run_git(
        ["ls-tree", "-z", "--full-tree", source_commit, "--", relative],
        f"review-subject tree entry {source_commit}:{relative}",
    )
    if not tree_entry.endswith(b"\x00") or tree_entry.count(b"\x00") != 1:
        fail(
            f"review subject {source_commit}:{relative} does not resolve to "
            "exactly one Git tree entry"
        )
    try:
        metadata, resolved_path = tree_entry[:-1].split(b"\t", 1)
        mode, entry_type, _object_id = metadata.split(b" ", 2)
        decoded_path = resolved_path.decode("utf-8", errors="strict")
    except (UnicodeDecodeError, ValueError):
        fail(f"review subject {source_commit}:{relative} has a malformed tree entry")
    if (
        decoded_path != relative
        or mode not in {b"100644", b"100755"}
        or entry_type != b"blob"
    ):
        fail(f"review subject {source_commit}:{relative} must be a regular Git blob")
    blob_spec = f"{source_commit}:{relative}"
    blob_type = (
        run_git(
            ["cat-file", "-t", blob_spec],
            f"review-subject blob {blob_spec}",
        )
        .decode("ascii", errors="strict")
        .strip()
    )
    if blob_type != "blob":
        fail(f"review subject {blob_spec} is not a Git blob")
    size_text = (
        run_git(
            ["cat-file", "-s", blob_spec],
            f"review-subject blob size {blob_spec}",
        )
        .decode("ascii", errors="strict")
        .strip()
    )
    try:
        size = int(size_text)
    except ValueError:
        fail(f"review subject {blob_spec} has an invalid Git blob size")
    if not 1 <= size <= MAX_JSON_BYTES:
        fail(f"review subject {blob_spec} byte size is outside 1..{MAX_JSON_BYTES}")
    content = run_git(
        ["cat-file", "blob", blob_spec], f"review-subject blob {blob_spec}"
    )
    if len(content) != size:
        fail(f"review subject {blob_spec} changed while it was resolved")
    return tree, content


def validate_hex(value: Any, pattern: re.Pattern[str], path: str) -> str:
    text = bounded_string(value, path, maximum=64)
    if not pattern.fullmatch(text):
        fail(f"{path} has an invalid lowercase hexadecimal identity")
    return text


def validate_timestamp(value: Any, path: str) -> datetime:
    text = bounded_string(value, path, minimum=20, maximum=20)
    if not UTC_TIMESTAMP.fullmatch(text):
        fail(f"{path} must be a second-resolution UTC timestamp ending in Z")
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as error:
        fail(f"{path} is not a real UTC timestamp: {error}")
    return parsed


def validate_identity(value: Any, path: str) -> str:
    identity = bounded_string(value, path, minimum=3, maximum=256)
    if not identity.isascii() or not IDENTITY_URI.fullmatch(identity):
        fail(f"{path} must be a stable ASCII issuer-and-subject URI")
    return identity


def validate_https_url(value: Any, path: str) -> str:
    url = bounded_string(value, path, minimum=12, maximum=512)
    if not url.isascii() or any(
        not 0x21 <= ord(character) <= 0x7E for character in url
    ):
        fail(f"{path} must use printable non-space ASCII")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        fail(
            f"{path} must be an absolute HTTPS URL without credentials, query, "
            "or fragment"
        )
    try:
        port = parsed.port
        parsed.hostname.encode("ascii")
    except (UnicodeError, ValueError) as error:
        fail(f"{path} has an invalid host or port: {error}")
    hostname = parsed.hostname.lower()
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        fail(f"{path} cannot use an IP-literal receipt host")
    labels = hostname.split(".")
    if (
        port not in {None, 443}
        or parsed.hostname != hostname
        or hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
        or len(hostname) > 253
        or len(labels) < 2
        or any(not DNS_LABEL.fullmatch(label) for label in labels)
        or labels[-1].isdigit()
    ):
        fail(
            f"{path} must use one canonical lowercase public DNS host and "
            "the default HTTPS port"
        )
    if not parsed.path.startswith("/") or parsed.path == "/":
        fail(f"{path} must identify one exact external receipt resource")
    return url


def read_retained_evidence(
    relative: str,
    path: str,
    *,
    artifact_overrides: dict[str, bytes] | None,
) -> bytes:
    if artifact_overrides is not None and relative in artifact_overrides:
        content = artifact_overrides[relative]
        if type(content) is not bytes:
            fail(f"{path} test override must be bytes")
        return content
    target = ROOT / relative
    try:
        return read_bounded_regular_file(
            target,
            limits=EVIDENCE_FILE_LIMITS,
            label=path,
        )
    except BoundedJsonError as error:
        fail(str(error))


def validate_evidence_ref(
    value: Any,
    path: str,
    *,
    artifact_overrides: dict[str, bytes] | None,
    evidence_cache: dict[str, bytes],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{path} must be an evidence-reference object")
    exact_keys(value, {"url", "path", "sha256", "bytes", "media_type"}, path)
    validate_https_url(value["url"], f"{path}.url")
    relative = relative_path(value["path"], f"{path}.path")
    if not relative.startswith(EVIDENCE_PREFIX):
        fail(f"{path}.path must be retained under {EVIDENCE_PREFIX}")
    expected_sha = validate_hex(value["sha256"], HEX64, f"{path}.sha256")
    expected_bytes = bounded_integer(
        value["bytes"], f"{path}.bytes", minimum=1, maximum=MAX_EVIDENCE_BYTES
    )
    media_type = bounded_string(value["media_type"], f"{path}.media_type", maximum=128)
    if not MEDIA_TYPE.fullmatch(media_type):
        fail(f"{path}.media_type is not a bounded lowercase media type")
    content = evidence_cache.get(relative)
    if content is None:
        content = read_retained_evidence(
            relative, f"{path}.path", artifact_overrides=artifact_overrides
        )
        if len(evidence_cache) >= MAX_UNIQUE_EVIDENCE_FILES:
            fail(
                "review evidence exceeds the aggregate limit of "
                f"{MAX_UNIQUE_EVIDENCE_FILES} unique files"
            )
        if (
            sum(map(len, evidence_cache.values())) + len(content)
            > MAX_TOTAL_EVIDENCE_BYTES
        ):
            fail(
                "review evidence exceeds the aggregate retained-byte limit of "
                f"{MAX_TOTAL_EVIDENCE_BYTES}"
            )
        evidence_cache[relative] = content
    if len(content) != expected_bytes:
        fail(f"{path}.bytes does not match retained evidence")
    if sha256_bytes(content) != expected_sha:
        fail(f"{path}.sha256 does not match retained evidence")
    return value


def validate_adr_markdown_byte_count(byte_count: int, path: str) -> int:
    if (
        type(byte_count) is not int
        or not MIN_ADR_MARKDOWN_BYTES <= byte_count <= MAX_ADR_MARKDOWN_BYTES
    ):
        fail(
            f"{path} byte size is outside "
            f"{MIN_ADR_MARKDOWN_BYTES}..{MAX_ADR_MARKDOWN_BYTES}"
        )
    return byte_count


def validate_adr_corpus_byte_counts(byte_counts: list[int]) -> int:
    total = 0
    for index, byte_count in enumerate(byte_counts):
        total += validate_adr_markdown_byte_count(
            byte_count, f"ADR corpus entry {index}"
        )
        if total > MAX_ADR_CORPUS_BYTES:
            fail(
                "ADR Markdown corpus exceeds the aggregate byte limit of "
                f"{MAX_ADR_CORPUS_BYTES}"
            )
    return total


def validate_markdown(
    decision: dict[str, Any], *, content_override: bytes | None = None
) -> tuple[str, int]:
    relative = decision["path"]
    if content_override is None:
        content = read_repository_regular_file(
            relative,
            maximum_bytes=MAX_ADR_MARKDOWN_BYTES,
            label=relative,
        )
    else:
        content = content_override
    validate_adr_markdown_byte_count(len(content), relative)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        fail(f"{relative} is not UTF-8: {error}")
    expected_heading = f"# {decision['id']} — {decision['title']}"
    if not text.startswith(expected_heading + "\n"):
        fail(f"{relative} does not start with {expected_heading!r}")
    if INVARIANT_STATUS not in text[:1024]:
        fail(f"{relative} lacks invariant registry-derived status metadata")
    if INVARIANT_NORMATIVE_EFFECT not in text[:1024]:
        fail(f"{relative} lacks invariant pre-promotion effect metadata")
    positions: list[int] = []
    for section in REQUIRED_SECTIONS:
        matches = list(re.finditer(rf"(?m)^{re.escape(section)}[ \t]*$", text))
        if len(matches) != 1:
            fail(
                f"{relative} requires exactly one heading {section!r}; "
                f"observed {len(matches)}"
            )
        positions.append(matches[0].start())
    if positions != sorted(positions):
        fail(f"{relative} required sections are out of order")
    ratification = text[text.index("## Ratification record") :]
    if not any(invariant in ratification for invariant in INVARIANT_RATIFICATIONS):
        fail(f"{relative} lacks the invariant external ratification record")
    lens = text[text.index("## Ten-lens review") : text.index("## Ratification record")]
    for number in range(1, 11):
        if not re.search(rf"(?m)^{number}\. ", lens):
            fail(f"{relative} lacks ten-lens item {number}")
    fences = extract_exact_json_fences(text, label=relative)
    if not fences:
        fail(f"{relative} must include at least one parseable JSON example")
    for index, fence in enumerate(fences):
        parse_json_fence(
            fence,
            label=f"{relative} JSON fence {index}",
            limits=ADR_FENCE_JSON_LIMITS,
        )
    return sha256_bytes(content), len(content)


def validate_module_markdown(
    decision_id: str,
    relative: str,
    *,
    content_override: bytes | None = None,
) -> tuple[str, int]:
    if content_override is None:
        content = read_repository_regular_file(
            relative,
            maximum_bytes=MAX_ADR_MARKDOWN_BYTES,
            label=relative,
        )
    else:
        content = content_override
    validate_adr_markdown_byte_count(len(content), relative)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        fail(f"{relative} is not UTF-8: {error}")
    if not text.startswith(f"# {decision_id} module — "):
        fail(f"{relative} does not start with the expected {decision_id} module title")
    invariant = f"> Status: PROPOSED and non-normative. Parent: {decision_id}."
    if invariant not in text[:1024]:
        fail(f"{relative} lacks invariant proposed module metadata")
    for index, fence in enumerate(extract_exact_json_fences(text, label=relative)):
        parse_json_fence(
            fence,
            label=f"{relative} JSON fence {index}",
            limits=ADR_FENCE_JSON_LIMITS,
        )
    return sha256_bytes(content), len(content)


def adr_source_set(decision_id: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    projection = {
        "schema": ADR_SOURCE_SET_SCHEMA,
        "decision_id": decision_id,
        "sources": sources,
    }
    payload = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        **projection,
        "digest_algorithm": "sha256(domain || u64be(projection_bytes) || projection)",
        "domain_hex": ADR_SOURCE_SET_DOMAIN.hex(),
        "sha256": sha256_bytes(
            ADR_SOURCE_SET_DOMAIN + len(payload).to_bytes(8, "big") + payload
        ),
    }


def validate_adr_source_set(
    value: Any,
    path: str,
    *,
    expected_decision_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{path} must be an ADR source-set object")
    exact_keys(
        value,
        {
            "schema",
            "decision_id",
            "sources",
            "digest_algorithm",
            "domain_hex",
            "sha256",
        },
        path,
    )
    if value["schema"] != ADR_SOURCE_SET_SCHEMA:
        fail(f"{path}.schema is not the ADR source-set schema")
    decision_id = bounded_string(value["decision_id"], f"{path}.decision_id", maximum=7)
    if decision_id not in EXPECTED_IDS:
        fail(f"{path}.decision_id is unknown")
    if expected_decision_id is not None and decision_id != expected_decision_id:
        fail(f"{path}.decision_id differs from the containing ADR")
    if (
        value["digest_algorithm"]
        != "sha256(domain || u64be(projection_bytes) || projection)"
        or value["domain_hex"] != ADR_SOURCE_SET_DOMAIN.hex()
    ):
        fail(f"{path} uses an unknown ADR source-set digest suite")
    sources = value["sources"]
    if (
        not isinstance(sources, list)
        or not 1 <= len(sources) <= MAX_ADR_MODULES_PER_DECISION + 1
    ):
        fail(
            f"{path}.sources must contain one main source and at most "
            f"{MAX_ADR_MODULES_PER_DECISION} modules"
        )
    seen_paths: set[str] = set()
    total = 0
    for index, source in enumerate(sources):
        source_path = f"{path}.sources[{index}]"
        if not isinstance(source, dict):
            fail(f"{source_path} must be an ADR source identity")
        exact_keys(source, {"kind", "path", "sha256", "bytes"}, source_path)
        expected_kind = "main" if index == 0 else "module"
        if source["kind"] != expected_kind:
            fail(f"{source_path}.kind must be {expected_kind!r}")
        relative = relative_path(source["path"], f"{source_path}.path")
        if relative in seen_paths:
            fail(f"{path}.sources contains duplicate paths")
        seen_paths.add(relative)
        if index == 0:
            match = ADR_MAIN_PATH.fullmatch(relative)
            path_decision_id = (
                f"ADR-{int(match.group(1)):03d}" if match is not None else None
            )
            if path_decision_id != decision_id:
                fail(f"{source_path}.path is not the matching ADR main Markdown")
        else:
            match = ADR_MODULE_PATH.fullmatch(relative)
            path_decision_id = (
                f"ADR-{int(match.group(1)):03d}" if match is not None else None
            )
            if path_decision_id != decision_id:
                fail(f"{source_path}.path is not a matching ADR companion module")
        validate_hex(source["sha256"], HEX64, f"{source_path}.sha256")
        total += validate_adr_markdown_byte_count(
            source["bytes"], f"{source_path}.bytes"
        )
        if total > MAX_ADR_CORPUS_BYTES:
            fail(
                f"{path}.sources exceeds the aggregate byte limit of "
                f"{MAX_ADR_CORPUS_BYTES}"
            )
    expected = adr_source_set(decision_id, copy.deepcopy(sources))
    if value != expected:
        fail(f"{path} differs from its canonical domain-separated digest")
    return value


def validate_required_review(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{path} must be a role-obligation object")
    exact_keys(
        value,
        {
            "role_id",
            "label",
            "min_distinct_identities",
            "requires_independence",
        },
        path,
    )
    role_id = bounded_string(value["role_id"], f"{path}.role_id", maximum=64)
    if not ROLE_ID.fullmatch(role_id):
        fail(f"{path}.role_id must be canonical lowercase kebab case")
    bounded_string(value["label"], f"{path}.label", minimum=3, maximum=128)
    bounded_integer(
        value["min_distinct_identities"],
        f"{path}.min_distinct_identities",
        minimum=1,
        maximum=8,
    )
    if not isinstance(value["requires_independence"], bool):
        fail(f"{path}.requires_independence must be boolean")
    return value


def validate_source(
    source: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        validate_native_json_tree(
            source,
            limits=REGISTRY_JSON_LIMITS,
            label="decision registry source",
        )
    except BoundedJsonError as error:
        fail(str(error))
    exact_keys(
        source,
        {
            "schema",
            "normative",
            "candidate",
            "wire_version",
            "task",
            "claim_boundary",
            "promotion_target",
            "promotion_blocked",
            "decisions",
            "review_records",
        },
        "$",
    )
    if source["schema"] != SOURCE_SCHEMA:
        fail("$.schema is not the proposed registry source schema")
    if source["normative"] is not False:
        fail("$.normative must be false")
    if source["candidate"] != "1.0.0-rc.1" or source["wire_version"] != "1.0":
        fail("$.candidate/wire_version differs from the frozen draft target")
    if source["task"] != "B01":
        fail("$.task must be B01")
    if source["claim_boundary"] != SOURCE_CLAIM_BOUNDARY:
        fail("$.claim_boundary differs from the fail-closed source claim boundary")
    if source["promotion_target"] != "contract/decision-registry.v1.json":
        fail("$.promotion_target differs from the reviewed target")
    if source["promotion_blocked"] is not True:
        fail("$.promotion_blocked must remain true")

    decisions = source["decisions"]
    if not isinstance(decisions, list) or len(decisions) != len(EXPECTED_IDS):
        fail("$.decisions must contain exactly ADR-001 through ADR-011")
    ids: list[str] = []
    paths: list[str] = []
    for index, decision in enumerate(decisions):
        path = f"$.decisions[{index}]"
        if not isinstance(decision, dict):
            fail(f"{path} must be an object")
        exact_keys(
            decision,
            {
                "id",
                "title",
                "path",
                "module_paths",
                "required_reviews",
                "defect_ids",
            },
            path,
        )
        identifier = bounded_string(decision["id"], f"{path}.id", maximum=7)
        if identifier not in EXPECTED_MODULE_PATHS:
            fail(f"{path}.id is not ADR-001 through ADR-011")
        ids.append(identifier)
        bounded_string(decision["title"], f"{path}.title", minimum=8, maximum=160)
        relative = relative_path(decision["path"], f"{path}.path")
        paths.append(relative)
        match = ADR_MAIN_PATH.fullmatch(relative)
        path_decision_id = (
            f"ADR-{int(match.group(1)):03d}" if match is not None else None
        )
        if path_decision_id != identifier:
            fail(f"{path}.path must be the matching canonical ADR Markdown path")
        module_paths = decision["module_paths"]
        if (
            not isinstance(module_paths, list)
            or len(module_paths) > MAX_ADR_MODULES_PER_DECISION
        ):
            fail(
                f"{path}.module_paths must contain at most "
                f"{MAX_ADR_MODULES_PER_DECISION} paths"
            )
        validated_module_paths = [
            relative_path(module_path, f"{path}.module_paths[{module_index}]")
            for module_index, module_path in enumerate(module_paths)
        ]
        if tuple(validated_module_paths) != EXPECTED_MODULE_PATHS[identifier]:
            fail(
                f"{path}.module_paths differs from the closed companion-module "
                f"inventory for {identifier}"
            )
        requirements = decision["required_reviews"]
        if not isinstance(requirements, list) or not 2 <= len(requirements) <= 16:
            fail(f"{path}.required_reviews must contain 2..16 role obligations")
        role_ids: list[str] = []
        for role_index, requirement in enumerate(requirements):
            validated = validate_required_review(
                requirement, f"{path}.required_reviews[{role_index}]"
            )
            role_ids.append(validated["role_id"])
        if len(role_ids) != len(set(role_ids)):
            fail(f"{path}.required_reviews contains duplicate role_id values")
        defects = decision["defect_ids"]
        if not isinstance(defects, list) or not 1 <= len(defects) <= 8:
            fail(f"{path}.defect_ids must contain 1..8 IDs")
        for defect in defects:
            if not isinstance(defect, str) or defect not in EXPECTED_DEFECTS:
                fail(f"{path}.defect_ids contains an unknown defect")
        if len(defects) != len(set(defects)):
            fail(f"{path}.defect_ids contains duplicate IDs")
    all_module_paths = [
        module_path
        for decision in decisions
        for module_path in decision["module_paths"]
    ]
    if (
        tuple(ids) != EXPECTED_IDS
        or len(paths) != len(set(paths))
        or len(all_module_paths) != len(set(all_module_paths))
        or set(paths).intersection(all_module_paths)
    ):
        fail("$.decisions IDs are missing/out of order or paths are duplicated")
    covered_defects = {
        defect for decision in decisions for defect in decision["defect_ids"]
    }
    if covered_defects != EXPECTED_DEFECTS:
        fail(
            "$.decisions defect coverage differs from D01..D20: "
            f"missing={sorted(EXPECTED_DEFECTS - covered_defects)}, "
            f"extra={sorted(covered_defects - EXPECTED_DEFECTS)}"
        )
    records = source["review_records"]
    if not isinstance(records, list) or len(records) > MAX_REVIEW_RECORDS:
        fail(f"$.review_records must contain at most {MAX_REVIEW_RECORDS} records")
    return decisions, records


def generated_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    generated: list[dict[str, Any]] = []
    for decision in decisions:
        digest, byte_count = validate_markdown(decision)
        sources = [
            {
                "kind": "main",
                "path": decision["path"],
                "sha256": digest,
                "bytes": byte_count,
            }
        ]
        for module_path in decision["module_paths"]:
            module_digest, module_bytes = validate_module_markdown(
                decision["id"], module_path
            )
            sources.append(
                {
                    "kind": "module",
                    "path": module_path,
                    "sha256": module_digest,
                    "bytes": module_bytes,
                }
            )
        source_set = adr_source_set(decision["id"], sources)
        validate_adr_source_set(
            source_set,
            f"generated.{decision['id']}.source_set",
            expected_decision_id=decision["id"],
        )
        generated.append(
            {
                **decision,
                "content_sha256": digest,
                "bytes": byte_count,
                "source_set": source_set,
            }
        )
    validate_adr_corpus_byte_counts(
        [
            source["bytes"]
            for decision in generated
            for source in decision["source_set"]["sources"]
        ]
    )
    return generated


def decision_set_projection(
    generated: list[dict[str, Any]],
    source: dict[str, Any],
    current_policy: dict[str, Any],
    closure_binding: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": DECISION_SET_SCHEMA,
        "candidate": source["candidate"],
        "wire_version": source["wire_version"],
        "review_policy": current_policy,
        "semantic_closure": copy.deepcopy(closure_binding),
        "decisions": [
            {
                "id": decision["id"],
                "title": decision["title"],
                "path": decision["path"],
                "module_paths": decision["module_paths"],
                "content_sha256": decision["content_sha256"],
                "bytes": decision["bytes"],
                "source_set": decision["source_set"],
                "required_reviews": decision["required_reviews"],
                "defect_ids": decision["defect_ids"],
            }
            for decision in generated
        ],
    }


def decision_set(
    generated: list[dict[str, Any]],
    source: dict[str, Any],
    current_policy: dict[str, Any],
    closure_binding: dict[str, Any],
) -> dict[str, Any]:
    projection = decision_set_projection(
        generated,
        source,
        current_policy,
        closure_binding,
    )
    payload = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = sha256_bytes(
        DECISION_SET_DOMAIN + len(payload).to_bytes(8, "big") + payload
    )
    return {
        "schema": DECISION_SET_SCHEMA,
        "digest_algorithm": "sha256(domain || u64be(projection_bytes) || projection)",
        "domain_hex": DECISION_SET_DOMAIN.hex(),
        "sha256": digest,
        "semantic_closure": closure_binding,
    }


def review_neutral_source(source: dict[str, Any]) -> dict[str, Any]:
    projection = copy.deepcopy(source)
    projection["review_records"] = []
    return projection


def validate_committed_review_inputs(
    source_commit: str,
    source_tree: str,
    generated: list[dict[str, Any]],
    source: dict[str, Any],
    current_policy: dict[str, Any],
    closure_binding: dict[str, Any],
    *,
    subject_resolver: SubjectResolver,
) -> dict[str, Any]:
    resolved_tree, committed_source_bytes = subject_resolver(
        source_commit, SOURCE_RELATIVE
    )
    if resolved_tree != source_tree:
        fail("review packet source tree differs from the committed decision source")
    committed_source = load_json_bytes(
        committed_source_bytes, f"{source_commit}:{SOURCE_RELATIVE}"
    )
    _, committed_records = validate_source(committed_source)
    if committed_records:
        fail("review packet source commit must contain zero review records")
    if committed_source != review_neutral_source(source):
        fail(
            "review packet source commit contains a stale decision, role, defect, "
            "claim, or promotion projection"
        )
    committed_source_identity = repository_file_identity(
        SOURCE, content_override=committed_source_bytes
    )

    for policy_key in ("generator", "output_json_schema"):
        identity = current_policy[policy_key]
        resolved_tree, committed_content = subject_resolver(
            source_commit, identity["path"]
        )
        if resolved_tree != source_tree:
            fail(
                "review packet source tree differs from the committed "
                f"{policy_key} input"
            )
        if (
            sha256_bytes(committed_content) != identity["sha256"]
            or len(committed_content) != identity["bytes"]
        ):
            fail(
                "review packet source commit does not contain the exact current "
                f"{policy_key} bytes"
            )

    for closure_key in ("source", "json_schema"):
        identity = closure_binding[closure_key]
        resolved_tree, committed_content = subject_resolver(
            source_commit, identity["path"]
        )
        if resolved_tree != source_tree:
            fail(
                "review packet source tree differs from the committed semantic "
                f"closure {closure_key} input"
            )
        if (
            sha256_bytes(committed_content) != identity["sha256"]
            or len(committed_content) != identity["bytes"]
        ):
            fail(
                "review packet source commit does not contain the exact current "
                f"semantic closure {closure_key} bytes"
            )

    for decision in generated:
        for source_identity in decision["source_set"]["sources"]:
            resolved_tree, resolved_content = subject_resolver(
                source_commit, source_identity["path"]
            )
            if resolved_tree != source_tree:
                fail(
                    "review packet source tree differs from the resolved commit "
                    f"tree for {decision['id']} source {source_identity['path']}"
                )
            if (
                sha256_bytes(resolved_content) != source_identity["sha256"]
                or len(resolved_content) != source_identity["bytes"]
            ):
                fail(
                    "review packet source commit does not contain the exact "
                    f"current {decision['id']} source {source_identity['path']}"
                )
    return committed_source_identity


def packet_subject_projection(
    generated: list[dict[str, Any]],
    current_set: dict[str, Any],
    current_policy: dict[str, Any],
    *,
    source_commit: str,
    source_tree: str,
    committed_source_identity: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": REVIEW_SUBJECT_SCHEMA,
        "state": "CURRENT",
        "normative": False,
        "claim_boundary": CLAIM_BOUNDARY,
        "promotion_blocked": True,
        "decision_set": current_set,
        "review_policy": current_policy,
        "source": {
            "commit": source_commit,
            "tree": source_tree,
            "decision_source": committed_source_identity,
        },
        "decisions": [
            {
                "id": decision["id"],
                "title": decision["title"],
                "path": decision["path"],
                "module_paths": decision["module_paths"],
                "content_sha256": decision["content_sha256"],
                "bytes": decision["bytes"],
                "source_set": decision["source_set"],
                "required_reviews": decision["required_reviews"],
                "defect_ids": decision["defect_ids"],
            }
            for decision in generated
        ],
    }


def parse_packet_subjects(
    packet_content: bytes,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not 1 <= len(packet_content) <= MAX_JSON_BYTES:
        fail(f"review packet byte size is outside 1..{MAX_JSON_BYTES}")
    try:
        text = packet_content.decode("utf-8")
    except UnicodeDecodeError as error:
        fail(f"{REVIEW_PACKET.relative_to(ROOT)} is not UTF-8: {error}")
    fences = extract_exact_json_fences(
        text, label=REVIEW_PACKET.relative_to(ROOT).as_posix()
    )
    if len(fences) > 64:
        fail("review packet contains more than 64 JSON fences")
    lifecycles: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for index, fence in enumerate(fences):
        value = parse_json_fence(
            fence,
            label=f"review packet JSON fence {index}",
            limits=REGISTRY_JSON_LIMITS,
        )
        if not isinstance(value, dict):
            continue
        if value.get("schema") == REVIEW_PACKET_LIFECYCLE_SCHEMA:
            lifecycles.append(value)
        elif value.get("schema") == REVIEW_SUBJECT_SCHEMA:
            candidates.append(value)
    if len(lifecycles) != 1:
        fail("review packet requires exactly one machine-readable lifecycle block")
    lifecycle = lifecycles[0]
    exact_keys(lifecycle, {"schema", "state"}, "review_packet.lifecycle")
    lifecycle_state = bounded_string(
        lifecycle["state"], "review_packet.lifecycle.state", maximum=10
    )
    if lifecycle_state not in {"CURRENT", "SUPERSEDED", "TEMPLATE"}:
        fail("review_packet.lifecycle.state is invalid")
    if lifecycle_state == "CURRENT" and len(candidates) != 1:
        fail(
            "a CURRENT review packet requires exactly one machine-readable "
            "review-subject block"
        )
    if lifecycle_state != "CURRENT" and candidates:
        fail("a non-current review packet cannot contain a CURRENT review subject")
    return lifecycle, candidates


def validate_current_packet_subject(
    packet_content: bytes,
    generated: list[dict[str, Any]],
    current_source: dict[str, Any],
    current_set: dict[str, Any],
    current_policy: dict[str, Any],
    *,
    subject_resolver: SubjectResolver,
    parsed_packet: tuple[dict[str, Any], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    lifecycle, candidates = parsed_packet or parse_packet_subjects(packet_content)
    if lifecycle["state"] != "CURRENT":
        fail("review records cannot target a non-current review packet")
    if len(candidates) != 1:
        fail(
            "review records require exactly one machine-readable CURRENT "
            "review-subject block in the packet"
        )
    block = candidates[0]
    exact_keys(
        block,
        {
            "schema",
            "state",
            "normative",
            "claim_boundary",
            "promotion_blocked",
            "decision_set",
            "review_policy",
            "source",
            "decisions",
        },
        "review_packet.subject",
    )
    source = block["source"]
    if not isinstance(source, dict):
        fail("review_packet.subject.source must be an object")
    exact_keys(
        source,
        {"commit", "tree", "decision_source"},
        "review_packet.subject.source",
    )
    source_commit = validate_hex(
        source["commit"], HEX40, "review_packet.subject.source.commit"
    )
    source_tree = validate_hex(
        source["tree"], HEX40, "review_packet.subject.source.tree"
    )
    committed_source_identity = validate_committed_review_inputs(
        source_commit,
        source_tree,
        generated,
        current_source,
        current_policy,
        current_set["semantic_closure"],
        subject_resolver=subject_resolver,
    )
    expected = packet_subject_projection(
        generated,
        current_set,
        current_policy,
        source_commit=source_commit,
        source_tree=source_tree,
        committed_source_identity=committed_source_identity,
    )
    if block != expected:
        fail(
            "review packet CURRENT subject differs from the exact current "
            "decision set, review policy, ADR inventory, or claim boundary"
        )
    return block


def validate_subject(
    value: Any, path: str, *, expected_decision_id: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{path} must be a review-subject object")
    exact_keys(
        value,
        {
            "decision_set_sha256",
            "adr_content_sha256",
            "adr_bytes",
            "adr_source_set",
            "source_commit",
            "source_tree",
            "review_packet_sha256",
        },
        path,
    )
    validate_hex(value["decision_set_sha256"], HEX64, f"{path}.decision_set_sha256")
    validate_hex(value["adr_content_sha256"], HEX64, f"{path}.adr_content_sha256")
    validate_adr_markdown_byte_count(value["adr_bytes"], f"{path}.adr_bytes")
    source_set = validate_adr_source_set(
        value["adr_source_set"],
        f"{path}.adr_source_set",
        expected_decision_id=expected_decision_id,
    )
    main_source = source_set["sources"][0]
    if (
        value["adr_content_sha256"] != main_source["sha256"]
        or value["adr_bytes"] != main_source["bytes"]
    ):
        fail(
            f"{path} main ADR digest and byte length differ from its source-set "
            "main identity"
        )
    validate_hex(value["source_commit"], HEX40, f"{path}.source_commit")
    validate_hex(value["source_tree"], HEX40, f"{path}.source_tree")
    validate_hex(value["review_packet_sha256"], HEX64, f"{path}.review_packet_sha256")
    return value


def validate_condition(
    value: Any,
    path: str,
    *,
    reviewer_identity: str,
    subject: dict[str, Any],
    review_timestamp: datetime,
    artifact_overrides: dict[str, bytes] | None,
    evidence_cache: dict[str, bytes],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{path} must be a condition object")
    exact_keys(
        value,
        {
            "condition_id",
            "statement",
            "status",
            "resolution_evidence",
            "closure",
        },
        path,
    )
    condition_id = bounded_string(
        value["condition_id"], f"{path}.condition_id", maximum=64
    )
    if not CONDITION_ID.fullmatch(condition_id):
        fail(f"{path}.condition_id must be canonical uppercase ASCII")
    bounded_string(value["statement"], f"{path}.statement", minimum=10, maximum=2048)
    status = bounded_string(value["status"], f"{path}.status", maximum=8)
    if status not in {"OPEN", "RESOLVED"}:
        fail(f"{path}.status must be OPEN or RESOLVED")
    evidence = value["resolution_evidence"]
    if not isinstance(evidence, list) or len(evidence) > MAX_EVIDENCE_PER_CONDITION:
        fail(
            f"{path}.resolution_evidence must contain at most "
            f"{MAX_EVIDENCE_PER_CONDITION} references"
        )
    for index, reference in enumerate(evidence):
        validate_evidence_ref(
            reference,
            f"{path}.resolution_evidence[{index}]",
            artifact_overrides=artifact_overrides,
            evidence_cache=evidence_cache,
        )
    closure = value["closure"]
    if status == "OPEN":
        if evidence or closure is not None:
            fail(f"{path} OPEN condition cannot contain resolution evidence or closure")
        return value
    if not evidence or not isinstance(closure, dict):
        fail(f"{path} RESOLVED condition requires evidence and a closure receipt")
    exact_keys(
        closure,
        {
            "reviewer_identity",
            "decision_set_sha256",
            "adr_content_sha256",
            "adr_source_set_sha256",
            "timestamp_utc",
            "external_receipt",
        },
        f"{path}.closure",
    )
    if (
        validate_identity(
            closure["reviewer_identity"], f"{path}.closure.reviewer_identity"
        )
        != reviewer_identity
    ):
        fail(f"{path}.closure must be attributed to the same reviewer identity")
    if closure["decision_set_sha256"] != subject["decision_set_sha256"]:
        fail(f"{path}.closure decision-set digest differs from the review subject")
    if closure["adr_content_sha256"] != subject["adr_content_sha256"]:
        fail(f"{path}.closure ADR digest differs from the review subject")
    validate_hex(
        closure["adr_source_set_sha256"],
        HEX64,
        f"{path}.closure.adr_source_set_sha256",
    )
    if closure["adr_source_set_sha256"] != subject["adr_source_set"]["sha256"]:
        fail(f"{path}.closure ADR source-set digest differs from the review subject")
    closed_at = validate_timestamp(
        closure["timestamp_utc"], f"{path}.closure.timestamp_utc"
    )
    if closed_at <= review_timestamp:
        fail(f"{path}.closure timestamp must be later than the review")
    validate_evidence_ref(
        closure["external_receipt"],
        f"{path}.closure.external_receipt",
        artifact_overrides=artifact_overrides,
        evidence_cache=evidence_cache,
    )
    return value


def validate_review_records(
    records: list[dict[str, Any]],
    generated: list[dict[str, Any]],
    current_set: dict[str, Any],
    current_packet: dict[str, Any],
    packet_subject: dict[str, Any],
    *,
    artifact_overrides: dict[str, bytes] | None,
    subject_resolver: SubjectResolver,
) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    decisions = {decision["id"]: decision for decision in generated}
    validated: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    review_timestamps: dict[str, datetime] = {}
    evidence_cache: dict[str, bytes] = {}
    resolved_subjects: dict[tuple[str, str], tuple[str, bytes]] = {}
    exclusive_evidence_paths: dict[str, str] = {}
    exclusive_evidence_urls: dict[str, str] = {}
    exclusive_evidence_digests: dict[str, str] = {}
    resolution_evidence_paths: set[str] = set()
    resolution_evidence_urls: set[str] = set()
    resolution_evidence_digests: set[str] = set()

    def reserve_exclusive_evidence(reference: dict[str, Any], owner: str) -> None:
        evidence_path = reference["path"]
        prior = exclusive_evidence_paths.get(evidence_path)
        if prior is not None:
            fail(f"{owner} reuses exclusive review evidence already bound by {prior}")
        evidence_url = reference["url"]
        prior = exclusive_evidence_urls.get(evidence_url)
        if prior is not None:
            fail(
                f"{owner} reuses an exclusive external receipt URL already "
                f"bound by {prior}"
            )
        evidence_digest = reference["sha256"]
        prior = exclusive_evidence_digests.get(evidence_digest)
        if prior is not None:
            fail(f"{owner} reuses exclusive receipt bytes already bound by {prior}")
        exclusive_evidence_paths[evidence_path] = owner
        exclusive_evidence_urls[evidence_url] = owner
        exclusive_evidence_digests[evidence_digest] = owner

    for index, record in enumerate(records):
        path = f"$.review_records[{index}]"
        if not isinstance(record, dict):
            fail(f"{path} must be an object")
        exact_keys(
            record,
            {
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
            },
            path,
        )
        review_id = bounded_string(
            record["review_id"], f"{path}.review_id", maximum=128
        )
        if not REVIEW_ID.fullmatch(review_id):
            fail(f"{path}.review_id is not canonical")
        if review_id in by_id:
            fail(f"$.review_records duplicates review_id {review_id}")
        adr_id = bounded_string(record["adr_id"], f"{path}.adr_id", maximum=7)
        if adr_id not in decisions:
            fail(f"{path}.adr_id is unknown")
        requirements = {
            requirement["role_id"]: requirement
            for requirement in decisions[adr_id]["required_reviews"]
        }
        role_id = bounded_string(record["role_id"], f"{path}.role_id", maximum=64)
        if role_id not in requirements:
            fail(f"{path}.role_id is not required by {adr_id}")

        reviewer = record["reviewer"]
        if not isinstance(reviewer, dict):
            fail(f"{path}.reviewer must be an object")
        exact_keys(
            reviewer,
            {
                "identity",
                "identity_kind",
                "independence_claimed",
                "implementation_owner_identities",
            },
            f"{path}.reviewer",
        )
        identity = validate_identity(reviewer["identity"], f"{path}.reviewer.identity")
        identity_kind = bounded_string(
            reviewer["identity_kind"], f"{path}.reviewer.identity_kind", maximum=6
        )
        if identity_kind not in {"PERSON", "TEAM"}:
            fail(f"{path}.reviewer.identity_kind must be PERSON or TEAM")
        if not isinstance(reviewer["independence_claimed"], bool):
            fail(f"{path}.reviewer.independence_claimed must be boolean")
        owners = reviewer["implementation_owner_identities"]
        if not isinstance(owners, list) or not 1 <= len(owners) <= 32:
            fail(
                f"{path}.reviewer.implementation_owner_identities must contain "
                "1..32 identities"
            )
        for owner_index, owner in enumerate(owners):
            validate_identity(
                owner,
                f"{path}.reviewer.implementation_owner_identities[{owner_index}]",
            )
        if len(owners) != len(set(owners)):
            fail(
                f"{path}.reviewer.implementation_owner_identities contains "
                "duplicate identities"
            )
        if reviewer["independence_claimed"] and identity in owners:
            fail(f"{path}.reviewer cannot self-assert independence from itself")

        subject = validate_subject(
            record["subject"],
            f"{path}.subject",
            expected_decision_id=adr_id,
        )
        if subject["review_packet_sha256"] == current_packet["sha256"]:
            packet_source = packet_subject["source"]
            if (
                subject["decision_set_sha256"] != current_set["sha256"]
                or subject["source_commit"] != packet_source["commit"]
                or subject["source_tree"] != packet_source["tree"]
                or subject["adr_content_sha256"] != decisions[adr_id]["content_sha256"]
                or subject["adr_bytes"] != decisions[adr_id]["bytes"]
                or subject["adr_source_set"] != decisions[adr_id]["source_set"]
            ):
                fail(
                    f"{path}.subject claims the current packet but differs from "
                    "its machine-readable review subject"
                )
        for source_identity in subject["adr_source_set"]["sources"]:
            subject_key = (subject["source_commit"], source_identity["path"])
            if subject_key not in resolved_subjects:
                resolved_subjects[subject_key] = subject_resolver(*subject_key)
            resolved_tree, resolved_content = resolved_subjects[subject_key]
            if resolved_tree != subject["source_tree"]:
                fail(
                    f"{path}.subject.source_tree differs from the resolved commit "
                    f"tree for {source_identity['path']}"
                )
            if sha256_bytes(resolved_content) != source_identity["sha256"]:
                fail(
                    f"{path}.subject ADR source-set digest differs from the "
                    f"resolved commit blob for {source_identity['path']}"
                )
            if len(resolved_content) != source_identity["bytes"]:
                fail(
                    f"{path}.subject ADR source-set byte length differs from the "
                    f"resolved commit blob for {source_identity['path']}"
                )
        decision = bounded_string(record["decision"], f"{path}.decision", maximum=22)
        if decision not in {"ACCEPT", "REJECT", "ACCEPT_WITH_CONDITIONS"}:
            fail(f"{path}.decision is unknown")
        review_timestamp = validate_timestamp(
            record["timestamp_utc"], f"{path}.timestamp_utc"
        )
        conditions = record["conditions"]
        if not isinstance(conditions, list) or len(conditions) > MAX_CONDITIONS:
            fail(f"{path}.conditions must contain at most {MAX_CONDITIONS} entries")
        condition_ids: list[str] = []
        for condition_index, condition in enumerate(conditions):
            validated_condition = validate_condition(
                condition,
                f"{path}.conditions[{condition_index}]",
                reviewer_identity=identity,
                subject=subject,
                review_timestamp=review_timestamp,
                artifact_overrides=artifact_overrides,
                evidence_cache=evidence_cache,
            )
            condition_ids.append(validated_condition["condition_id"])
        if len(condition_ids) != len(set(condition_ids)):
            fail(f"{path}.conditions contains duplicate condition IDs")
        if decision == "ACCEPT_WITH_CONDITIONS" and not conditions:
            fail(f"{path} conditional acceptance requires at least one condition")
        if decision in {"ACCEPT", "REJECT"} and conditions:
            fail(f"{path} {decision} cannot contain conditions")
        validate_evidence_ref(
            record["role_authorization"],
            f"{path}.role_authorization",
            artifact_overrides=artifact_overrides,
            evidence_cache=evidence_cache,
        )
        validate_evidence_ref(
            record["external_receipt"],
            f"{path}.external_receipt",
            artifact_overrides=artifact_overrides,
            evidence_cache=evidence_cache,
        )
        if record["role_authorization"]["path"] == record["external_receipt"]["path"]:
            fail(
                f"{path}.role_authorization and external_receipt must use "
                "separate retained evidence files"
            )
        reserve_exclusive_evidence(
            record["role_authorization"], f"{path}.role_authorization"
        )
        reserve_exclusive_evidence(
            record["external_receipt"], f"{path}.external_receipt"
        )
        independence_assessment = record["independence_assessment"]
        if reviewer["independence_claimed"]:
            validate_evidence_ref(
                independence_assessment,
                f"{path}.independence_assessment",
                artifact_overrides=artifact_overrides,
                evidence_cache=evidence_cache,
            )
            if independence_assessment["path"] in {
                record["role_authorization"]["path"],
                record["external_receipt"]["path"],
            }:
                fail(
                    f"{path}.independence_assessment must use a separate retained "
                    "evidence file"
                )
            reserve_exclusive_evidence(
                independence_assessment,
                f"{path}.independence_assessment",
            )
        elif independence_assessment is not None:
            fail(
                f"{path}.independence_assessment requires "
                "reviewer.independence_claimed=true"
            )
        record_evidence_paths = {
            record["role_authorization"]["path"],
            record["external_receipt"]["path"],
        }
        if independence_assessment is not None:
            record_evidence_paths.add(independence_assessment["path"])
        condition_closure_paths: set[str] = set()
        for condition_index, condition in enumerate(conditions):
            condition_path = f"{path}.conditions[{condition_index}]"
            resolution_paths = [
                reference["path"] for reference in condition["resolution_evidence"]
            ]
            resolution_evidence_paths.update(resolution_paths)
            resolution_evidence_urls.update(
                reference["url"] for reference in condition["resolution_evidence"]
            )
            resolution_evidence_digests.update(
                reference["sha256"] for reference in condition["resolution_evidence"]
            )
            if len(resolution_paths) != len(set(resolution_paths)):
                fail(f"{condition_path}.resolution_evidence contains duplicate paths")
            if record_evidence_paths.intersection(resolution_paths):
                fail(
                    f"{condition_path}.resolution_evidence must be separate from "
                    "review, role-authorization, and independence evidence"
                )
            if condition["closure"] is None:
                continue
            closure_path = condition["closure"]["external_receipt"]["path"]
            if (
                closure_path in record_evidence_paths
                or closure_path in resolution_paths
                or closure_path in condition_closure_paths
            ):
                fail(
                    f"{condition_path}.closure must use a distinct retained "
                    "same-reviewer receipt"
                )
            condition_closure_paths.add(closure_path)
            reserve_exclusive_evidence(
                condition["closure"]["external_receipt"],
                f"{condition_path}.closure.external_receipt",
            )
        supersedes = record["supersedes"]
        if supersedes is not None:
            supersedes = bounded_string(supersedes, f"{path}.supersedes", maximum=128)
            if not REVIEW_ID.fullmatch(supersedes) or supersedes == review_id:
                fail(f"{path}.supersedes is invalid")
        by_id[review_id] = record
        review_timestamps[review_id] = review_timestamp
        validated.append(record)

    overlap = resolution_evidence_paths & set(exclusive_evidence_paths)
    if overlap:
        fail(
            "condition resolution evidence reuses an exclusive review, role, "
            f"independence, or closure receipt: {sorted(overlap)}"
        )
    if resolution_evidence_urls & set(exclusive_evidence_urls):
        fail("condition resolution evidence reuses an exclusive external receipt URL")
    if resolution_evidence_digests & set(exclusive_evidence_digests):
        fail("condition resolution evidence reuses exclusive external receipt bytes")

    children: dict[str, set[str]] = {review_id: set() for review_id in by_id}
    for record in validated:
        predecessor_id = record["supersedes"]
        if predecessor_id is None:
            continue
        predecessor = by_id.get(predecessor_id)
        if predecessor is None:
            fail(f"review {record['review_id']} supersedes an unknown review")
        current_key = (
            record["adr_id"],
            record["role_id"],
            record["reviewer"]["identity"],
        )
        predecessor_key = (
            predecessor["adr_id"],
            predecessor["role_id"],
            predecessor["reviewer"]["identity"],
        )
        if current_key != predecessor_key:
            fail(
                f"review {record['review_id']} can supersede only the same "
                "ADR/role/reviewer chain"
            )
        if review_timestamps[record["review_id"]] <= review_timestamps[predecessor_id]:
            fail(
                f"review {record['review_id']} must have a later timestamp than "
                f"its predecessor {predecessor_id}"
            )
        children[predecessor_id].add(record["review_id"])
        if len(children[predecessor_id]) > 1:
            fail(f"review chain forks after {predecessor_id}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(review_id: str) -> None:
        if review_id in visited:
            return
        if review_id in visiting:
            fail(f"review supersession cycle includes {review_id}")
        visiting.add(review_id)
        predecessor = by_id[review_id]["supersedes"]
        if predecessor is not None:
            visit(predecessor)
        visiting.remove(review_id)
        visited.add(review_id)

    for review_id in by_id:
        visit(review_id)

    active_by_key: dict[tuple[str, str, str], list[str]] = {}
    for review_id, record in by_id.items():
        if children[review_id]:
            continue
        key = (
            record["adr_id"],
            record["role_id"],
            record["reviewer"]["identity"],
        )
        active_by_key.setdefault(key, []).append(review_id)
    for key, active_ids in active_by_key.items():
        if len(active_ids) > 1:
            fail(f"parallel active review chains exist for {key}: {sorted(active_ids)}")

    derived: list[dict[str, Any]] = []
    for record in validated:
        decision = decisions[record["adr_id"]]
        requirement = next(
            requirement
            for requirement in decision["required_reviews"]
            if requirement["role_id"] == record["role_id"]
        )
        stale_reasons: list[str] = []
        if record["subject"]["decision_set_sha256"] != current_set["sha256"]:
            stale_reasons.append("DECISION_SET_DIGEST_MISMATCH")
        if record["subject"]["adr_content_sha256"] != decision["content_sha256"]:
            stale_reasons.append("ADR_CONTENT_DIGEST_MISMATCH")
        if record["subject"]["adr_bytes"] != decision["bytes"]:
            stale_reasons.append("ADR_BYTE_LENGTH_MISMATCH")
        if (
            record["subject"]["adr_source_set"]["sha256"]
            != decision["source_set"]["sha256"]
        ):
            stale_reasons.append("ADR_SOURCE_SET_DIGEST_MISMATCH")
        if record["subject"]["review_packet_sha256"] != current_packet["sha256"]:
            stale_reasons.append("REVIEW_PACKET_DIGEST_MISMATCH")
        active = not children[record["review_id"]]
        all_conditions_resolved = all(
            condition["status"] == "RESOLVED" for condition in record["conditions"]
        )
        accepting_decision = record["decision"] == "ACCEPT" or (
            record["decision"] == "ACCEPT_WITH_CONDITIONS" and all_conditions_resolved
        )
        independence_sufficient = not requirement["requires_independence"] or (
            record["reviewer"]["independence_claimed"]
            and record["independence_assessment"] is not None
        )
        qualifies = (
            active
            and not stale_reasons
            and accepting_decision
            and independence_sufficient
        )
        derived.append(
            {
                **record,
                "derived": {
                    "active": active,
                    "current_subject": not stale_reasons,
                    "qualifying_acceptance": qualifies,
                    "stale_reasons": stale_reasons,
                },
            }
        )
    return derived, children


def acceptance_blockers(
    decision: dict[str, Any], records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    decision_records = [
        record for record in records if record["adr_id"] == decision["id"]
    ]
    for requirement in decision["required_reviews"]:
        qualifying = [
            record
            for record in decision_records
            if record["role_id"] == requirement["role_id"]
            and record["derived"]["qualifying_acceptance"]
        ]
        identities = sorted({record["reviewer"]["identity"] for record in qualifying})
        if len(identities) < requirement["min_distinct_identities"]:
            blockers.append(
                {
                    "code": "MISSING_ROLE_ACCEPTANCE",
                    "role_id": requirement["role_id"],
                    "review_ids": [record["review_id"] for record in qualifying],
                    "detail": (
                        f"requires {requirement['min_distinct_identities']} distinct "
                        f"qualifying identities; observed {len(identities)}"
                    ),
                }
            )
    for record in decision_records:
        if not record["derived"]["active"] or not record["derived"]["current_subject"]:
            continue
        if record["decision"] == "REJECT":
            blockers.append(
                {
                    "code": "ACTIVE_REJECT",
                    "role_id": record["role_id"],
                    "review_ids": [record["review_id"]],
                    "detail": (
                        "an active same-subject reviewer rejection blocks acceptance"
                    ),
                }
            )
        if record["decision"] == "ACCEPT_WITH_CONDITIONS" and any(
            condition["status"] != "RESOLVED" for condition in record["conditions"]
        ):
            blockers.append(
                {
                    "code": "UNRESOLVED_CONDITION",
                    "role_id": record["role_id"],
                    "review_ids": [record["review_id"]],
                    "detail": "an active same-subject conditional review remains open",
                }
            )
        requirement = next(
            requirement
            for requirement in decision["required_reviews"]
            if requirement["role_id"] == record["role_id"]
        )
        if requirement["requires_independence"] and (
            not record["reviewer"]["independence_claimed"]
            or record["independence_assessment"] is None
        ):
            blockers.append(
                {
                    "code": "INDEPENDENCE_NOT_ESTABLISHED",
                    "role_id": record["role_id"],
                    "review_ids": [record["review_id"]],
                    "detail": (
                        "this role requires an explicit independence claim and "
                        "a separate retained assessment"
                    ),
                }
            )
    return blockers


def build_registry(
    source: dict[str, Any] | None = None,
    *,
    artifact_overrides: dict[str, bytes] | None = None,
    closure_source_override: dict[str, Any] | None = None,
    closure_schema_override: bytes | None = None,
    closure_artifact_overrides: dict[str, bytes] | None = None,
    subject_resolver: SubjectResolver = resolve_git_subject,
    policy_overrides: dict[str, bytes] | None = None,
    packet_override: bytes | None = None,
) -> dict[str, Any]:
    if source is None:
        try:
            source_content = read_bounded_regular_file(
                SOURCE,
                limits=REGISTRY_FILE_LIMITS,
                label=SOURCE_RELATIVE,
            )
        except BoundedJsonError as error:
            fail(str(error))
        value = load_json_bytes(source_content, SOURCE_RELATIVE)
    else:
        try:
            validate_native_json_tree(
                source,
                limits=REGISTRY_JSON_LIMITS,
                label="decision registry source override",
            )
        except BoundedJsonError as error:
            fail(str(error))
        value = copy.deepcopy(source)
        source_content = source_bytes(value)
    decisions, review_records = validate_source(value)
    generated = generated_decisions(decisions)
    current_policy = review_policy(policy_overrides)
    closure_requirements = load_closure_requirements(
        generated,
        source_override=closure_source_override,
        schema_override=closure_schema_override,
    )
    if packet_override is not None and not isinstance(packet_override, bytes):
        fail("review-packet test override must be bytes")
    if packet_override is None:
        try:
            packet_content = read_bounded_regular_file(
                REVIEW_PACKET,
                limits=REGISTRY_FILE_LIMITS,
                label=REVIEW_PACKET.relative_to(ROOT).as_posix(),
            )
        except BoundedJsonError as error:
            fail(str(error))
        current_packet = repository_file_identity(
            REVIEW_PACKET,
            content_override=packet_content,
        )
    else:
        packet_content = packet_override
        current_packet = repository_file_identity(
            REVIEW_PACKET, content_override=packet_content
        )
    current_set = decision_set(
        generated,
        value,
        current_policy,
        closure_requirements["binding"],
    )
    closure_evaluation, closure_observations = evaluate_semantic_closure(
        closure_requirements,
        generated,
        value,
        current_policy,
        current_set,
        artifact_overrides=closure_artifact_overrides,
    )
    parsed_packet = parse_packet_subjects(packet_content)
    packet_lifecycle = parsed_packet[0]
    if review_records and packet_lifecycle["state"] != "CURRENT":
        fail("review records require a CURRENT machine-readable packet lifecycle")
    packet_subject = (
        validate_current_packet_subject(
            packet_content,
            generated,
            value,
            current_set,
            current_policy,
            subject_resolver=subject_resolver,
            parsed_packet=parsed_packet,
        )
        if packet_lifecycle["state"] == "CURRENT"
        else None
    )
    reviews, _ = validate_review_records(
        review_records,
        generated,
        current_set,
        current_packet,
        packet_subject,
        artifact_overrides=artifact_overrides,
        subject_resolver=subject_resolver,
    )
    closure_blockers_by_id: dict[str, list[dict[str, Any]]] = {}
    for decision in generated:
        closure_blockers = semantic_closure_blockers(
            decision,
            closure_requirements["by_id"][decision["id"]],
            closure_evaluation,
            closure_observations,
        )
        closure_blockers_by_id[decision["id"]] = closure_blockers
    any_closure_blocker = any(closure_blockers_by_id.values())
    closure_evaluation["state"] = "OPEN" if any_closure_blocker else "CLOSED"

    finalized: list[dict[str, Any]] = []
    for decision in generated:
        closure_blockers = closure_blockers_by_id[decision["id"]]
        if any_closure_blocker:
            closure_blockers = [
                {
                    "code": "SEMANTIC_CLOSURE_OPEN",
                    "closure_id": "B01-SEMANTIC-CLOSURE",
                    "detail": (
                        "B01 semantic closure remains open; no architecture "
                        "decision can be accepted"
                    ),
                },
                *closure_blockers,
            ]
        blockers = [*closure_blockers, *acceptance_blockers(decision, reviews)]
        finalized.append(
            {
                **decision,
                "status": "ACCEPTED" if not blockers else "PROPOSED",
                "acceptance_blockers": blockers,
            }
        )
    if PROMOTION_TARGET.exists():
        fail(
            "contract/decision-registry.v1.json exists while this non-normative "
            "B01 staging tool still owns the review subject"
        )
    return {
        "schema": OUTPUT_SCHEMA,
        "normative": False,
        "candidate": value["candidate"],
        "wire_version": value["wire_version"],
        "task": value["task"],
        "claim_boundary": CLAIM_BOUNDARY,
        "generated_by": GENERATOR,
        "source": {
            "path": SOURCE_RELATIVE,
            "sha256": sha256_bytes(source_content),
            "bytes": len(source_content),
        },
        "review_policy": current_policy,
        "review_packet": current_packet,
        "review_packet_lifecycle": packet_lifecycle,
        "review_packet_subject": packet_subject,
        "decision_set": current_set,
        "semantic_closure_evaluation": closure_evaluation,
        "promotion_target": value["promotion_target"],
        "promotion_blocked": True,
        "counts": {
            "decisions": len(finalized),
        },
        "decisions": finalized,
        "review_records": reviews,
    }


def generated_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def validate_generated(value: dict[str, Any], expected: dict[str, Any]) -> None:
    if value != expected:
        fail("generated proposed decision registry differs from exact expected content")
    if value.get("schema") != OUTPUT_SCHEMA or value.get("normative") is not False:
        fail("generated registry overclaims schema or normative status")
    if value.get("promotion_blocked") is not True:
        fail("generated registry does not block promotion")
    counts = value.get("counts")
    if counts != {"decisions": len(EXPECTED_IDS)}:
        fail("generated registry static decision count is inconsistent")
    closure_evaluation = value.get("semantic_closure_evaluation")
    if not isinstance(closure_evaluation, dict):
        fail("generated registry semantic-closure evaluation is missing")
    if value["decision_set"]["semantic_closure"] != {
        "source": closure_evaluation.get("source"),
        "json_schema": closure_evaluation.get("json_schema"),
    }:
        fail("generated registry semantic-closure binding differs from evaluation")
    if closure_evaluation.get("decision_set_sha256") != value["decision_set"]["sha256"]:
        fail("generated registry semantic-closure evaluation is stale")
    accepted = sum(
        decision.get("status") == "ACCEPTED" for decision in value["decisions"]
    )
    if closure_evaluation.get("state") == "OPEN" and accepted != 0:
        fail("generated registry accepts a decision while semantic closure is OPEN")
    if closure_evaluation.get("state") == "CLOSED":
        if (
            closure_evaluation.get("semantic_corpus", {}).get("observed_status")
            != "COMPLETE_CURRENT"
            or closure_evaluation.get("b03_deferrals", {}).get("observed_status")
            != "COMPLETE_ENVELOPES_VERIFIED"
        ):
            fail("generated registry reports CLOSED with incomplete closure evidence")
    validate_adr_corpus_byte_counts(
        [
            source["bytes"]
            for decision in value["decisions"]
            for source in decision["source_set"]["sources"]
        ]
    )
    for decision in value["decisions"]:
        source_set = validate_adr_source_set(
            decision["source_set"],
            f"generated.{decision['id']}.source_set",
            expected_decision_id=decision["id"],
        )
        if (
            source_set["sources"][0]["path"] != decision["path"]
            or source_set["sources"][0]["sha256"] != decision["content_sha256"]
            or source_set["sources"][0]["bytes"] != decision["bytes"]
            or [source["path"] for source in source_set["sources"][1:]]
            != decision["module_paths"]
        ):
            fail("generated registry ADR source set differs from its decision fields")
        if decision["status"] not in {"PROPOSED", "ACCEPTED"}:
            fail("generated registry contains an unknown decision status")
        if decision["status"] == "ACCEPTED" and decision["acceptance_blockers"]:
            fail("generated registry optimistically accepts a blocked decision")
        if decision["status"] == "PROPOSED" and not decision["acceptance_blockers"]:
            fail("generated registry proposes a decision without a blocker")
        if not HEX64.fullmatch(decision["content_sha256"]):
            fail("generated registry contains an invalid content digest")


def validate_output_schema_limits(value: dict[str, Any]) -> None:
    definitions = value.get("$defs")
    if not isinstance(definitions, dict):
        fail("output JSON Schema lacks $defs")
    for definition, field in (
        ("packetDecision", "bytes"),
        ("decision", "bytes"),
        ("reviewSubject", "adr_bytes"),
    ):
        try:
            constraint = definitions[definition]["properties"][field]
        except (KeyError, TypeError):
            fail(
                "output JSON Schema lacks the ADR byte constraint at "
                f"$defs.{definition}.properties.{field}"
            )
        if constraint != {
            "type": "integer",
            "minimum": MIN_ADR_MARKDOWN_BYTES,
            "maximum": MAX_ADR_MARKDOWN_BYTES,
        }:
            fail(
                "output JSON Schema ADR byte constraint differs at "
                f"$defs.{definition}.properties.{field}"
            )
    try:
        source_constraint = definitions["adrSource"]["properties"]["bytes"]
        source_items = definitions["adrSourceSet"]["properties"]["sources"]
    except (KeyError, TypeError):
        fail("output JSON Schema lacks bounded ADR source-set definitions")
    if source_constraint != {
        "type": "integer",
        "minimum": MIN_ADR_MARKDOWN_BYTES,
        "maximum": MAX_ADR_MARKDOWN_BYTES,
    }:
        fail("output JSON Schema ADR source byte constraint differs")
    if (
        source_items.get("minItems") != 1
        or source_items.get("maxItems") != MAX_ADR_MODULES_PER_DECISION + 1
    ):
        fail("output JSON Schema ADR source-set cardinality differs")


def must_fail(action: Any, description: str) -> None:
    try:
        action()
    except RegistryError:
        return
    raise AssertionError(f"hostile self-test passed: {description}")


def test_evidence_content(relative: str, content: bytes) -> bytes:
    if len(content) >= MAX_EVIDENCE_BYTES:
        return content
    return (
        json.dumps(
            {
                "base_sha256": sha256_bytes(content),
                "path": relative,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def test_evidence_ref(name: str, content: bytes) -> dict[str, Any]:
    slug = sha256_bytes(name.encode("utf-8"))[:16]
    relative = f"{EVIDENCE_PREFIX}self-test-{slug}.json"
    retained = test_evidence_content(relative, content)
    return {
        "url": f"https://reviews.example.test/{name}",
        "path": relative,
        "sha256": sha256_bytes(retained),
        "bytes": len(retained),
        "media_type": "application/json",
    }


def test_artifact_overrides(value: Any, content: bytes) -> dict[str, bytes]:
    overrides: dict[str, bytes] = {}

    def visit(member: Any) -> None:
        if isinstance(member, dict):
            if {
                "url",
                "path",
                "sha256",
                "bytes",
                "media_type",
            }.issubset(member) and isinstance(member.get("path"), str):
                overrides[member["path"]] = test_evidence_content(
                    member["path"], content
                )
            for nested in member.values():
                visit(nested)
        elif isinstance(member, list):
            for nested in member:
                visit(nested)

    visit(value)
    return overrides


def test_review(
    *,
    review_id: str,
    adr_id: str,
    requirement: dict[str, Any],
    registry: dict[str, Any],
    content: bytes,
    identity_suffix: str,
    decision: str = "ACCEPT",
    supersedes: str | None = None,
) -> dict[str, Any]:
    adr = next(item for item in registry["decisions"] if item["id"] == adr_id)
    identity = f"urn:ncp:test-reviewer:{identity_suffix}"
    return {
        "review_id": review_id,
        "adr_id": adr_id,
        "role_id": requirement["role_id"],
        "reviewer": {
            "identity": identity,
            "identity_kind": "PERSON",
            "independence_claimed": requirement["requires_independence"],
            "implementation_owner_identities": [
                "urn:ncp:test-implementation-owner:one"
            ],
        },
        "subject": {
            "decision_set_sha256": registry["decision_set"]["sha256"],
            "adr_content_sha256": adr["content_sha256"],
            "adr_bytes": adr["bytes"],
            "adr_source_set": copy.deepcopy(adr["source_set"]),
            "source_commit": "1" * 40,
            "source_tree": "2" * 40,
            "review_packet_sha256": registry["review_packet"]["sha256"],
        },
        "decision": decision,
        "conditions": [],
        "role_authorization": test_evidence_ref(
            f"{review_id}/role-authorization", content
        ),
        "independence_assessment": (
            test_evidence_ref(f"{review_id}/independence-assessment", content)
            if requirement["requires_independence"]
            else None
        ),
        "external_receipt": test_evidence_ref(f"{review_id}/review", content),
        "timestamp_utc": "2026-07-26T12:00:00Z",
        "supersedes": supersedes,
    }


def test_subject_resolver(
    source_commit: str, repository_path: str
) -> tuple[str, bytes]:
    if source_commit != "1" * 40:
        fail("self-test subject resolver rejected an unknown source commit")
    return "2" * 40, (ROOT / repository_path).read_bytes()


def test_decision_source_identity() -> dict[str, Any]:
    return repository_file_identity(SOURCE)


def test_packet_content(
    registry: dict[str, Any],
    *,
    block_override: dict[str, Any] | None = None,
    state: str = "CURRENT",
) -> bytes:
    if state not in {"CURRENT", "SUPERSEDED", "TEMPLATE"}:
        raise AssertionError(f"unknown self-test packet state {state}")
    lifecycle = {
        "schema": REVIEW_PACKET_LIFECYCLE_SCHEMA,
        "state": state,
    }
    text = (
        "# B01 self-test review packet\n\n"
        "```json\n" + json.dumps(lifecycle, ensure_ascii=False, indent=2) + "\n```\n"
    )
    if state == "CURRENT":
        block = block_override or packet_subject_projection(
            registry["decisions"],
            registry["decision_set"],
            registry["review_policy"],
            source_commit="1" * 40,
            source_tree="2" * 40,
            committed_source_identity=test_decision_source_identity(),
        )
        text += (
            "```json\n" + json.dumps(block, ensure_ascii=False, indent=2) + "\n```\n"
        )
    return text.encode("utf-8")


def self_test_adr_byte_limits(source: dict[str, Any]) -> None:
    decision = copy.deepcopy(source["decisions"][0])
    original = (ROOT / decision["path"]).read_bytes()
    if len(original) > MAX_ADR_MARKDOWN_BYTES:
        raise AssertionError("self-test ADR already exceeds the Markdown byte limit")
    at_markdown_cap = original + b" " * (MAX_ADR_MARKDOWN_BYTES - len(original))
    validate_markdown(decision, content_override=at_markdown_cap)
    must_fail(
        lambda: validate_markdown(decision, content_override=at_markdown_cap + b" "),
        "ADR Markdown cap plus one byte",
    )
    module_decision = source["decisions"][3]
    module_path = module_decision["module_paths"][0]
    original_module = (ROOT / module_path).read_bytes()
    at_module_cap = original_module + b" " * (
        MAX_ADR_MARKDOWN_BYTES - len(original_module)
    )
    validate_module_markdown(
        module_decision["id"],
        module_path,
        content_override=at_module_cap,
    )
    must_fail(
        lambda: validate_module_markdown(
            module_decision["id"],
            module_path,
            content_override=at_module_cap + b" ",
        ),
        "ADR module Markdown cap plus one byte",
    )


def self_test_json_fence_scanner() -> None:
    markdown = (
        "```text\n"
        "```json\n"
        '{"ignored":true}\n'
        "```\n"
        "```json\r\n"
        '{"accepted":true}\r\n'
        "```\r\n"
    )
    if extract_exact_json_fences(markdown, label="self-test Markdown") != [
        '{"accepted":true}'
    ]:
        raise AssertionError("exact JSON fence scanner accepted a nested marker")
    must_fail(
        lambda: extract_exact_json_fences(
            "```json\n{}\n", label="self-test unclosed Markdown"
        ),
        "unclosed exact JSON fence",
    )
    aggregate_at_cap = [MAX_ADR_MARKDOWN_BYTES] * 7 + [
        MAX_ADR_MARKDOWN_BYTES - 5 * MIN_ADR_MARKDOWN_BYTES,
        *([MIN_ADR_MARKDOWN_BYTES] * 5),
    ]
    if validate_adr_corpus_byte_counts(aggregate_at_cap) != MAX_ADR_CORPUS_BYTES:
        raise AssertionError("ADR Markdown corpus exact-cap test is malformed")
    aggregate_over_cap = aggregate_at_cap.copy()
    aggregate_over_cap[7] += 1
    must_fail(
        lambda: validate_adr_corpus_byte_counts(aggregate_over_cap),
        "ADR Markdown corpus cap plus one byte",
    )
    validate_output_schema_limits(load_json(SCHEMA))


def self_test_physical_source_paths() -> None:
    with tempfile.TemporaryDirectory(prefix="ncp-adr-source-self-test-") as temporary:
        root = Path(temporary).resolve(strict=True)
        module_directory = root / "docs" / "adr" / "modules"
        module_directory.mkdir(parents=True)
        regular = module_directory / "regular.md"
        regular.write_bytes(b"# bounded physical source\n")
        relative = "docs/adr/modules/regular.md"
        if (
            read_physical_regular_file(
                root,
                relative,
                maximum_bytes=1024,
                label="self-test regular source",
            )
            != b"# bounded physical source\n"
        ):
            raise AssertionError("physical source reader changed stable bytes")

        leaf_symlink = module_directory / "leaf-symlink.md"
        leaf_symlink.symlink_to(regular.name)
        must_fail(
            lambda: read_physical_regular_file(
                root,
                "docs/adr/modules/leaf-symlink.md",
                maximum_bytes=1024,
                label="self-test leaf symlink",
            ),
            "ADR module leaf symlink",
        )

        real_directory = root / "real-modules"
        real_directory.mkdir()
        (real_directory / "ancestor.md").write_bytes(b"# ancestor target\n")
        ancestor_symlink = root / "docs" / "adr" / "linked-modules"
        ancestor_symlink.symlink_to(real_directory, target_is_directory=True)
        must_fail(
            lambda: read_physical_regular_file(
                root,
                "docs/adr/linked-modules/ancestor.md",
                maximum_bytes=1024,
                label="self-test ancestor symlink",
            ),
            "ADR module ancestor symlink",
        )

        race_directory = root / "docs" / "adr" / "race-modules"
        race_directory.mkdir()
        (race_directory / "race.md").write_bytes(b"# original race source\n")
        displaced_directory = root / "docs" / "adr" / "race-modules-displaced"

        def replace_ancestor(phase: str) -> None:
            if phase != "read-complete":
                return
            race_directory.rename(displaced_directory)
            race_directory.mkdir()
            (race_directory / "race.md").write_bytes(b"# replacement source\n")

        must_fail(
            lambda: read_physical_regular_file(
                root,
                "docs/adr/race-modules/race.md",
                maximum_bytes=1024,
                label="self-test replaced ancestor",
                phase_hook=replace_ancestor,
            ),
            "ADR module ancestor replacement during read",
        )

        hard_link = module_directory / "hard-link.md"
        os.link(regular, hard_link)
        must_fail(
            lambda: read_physical_regular_file(
                root,
                relative,
                maximum_bytes=1024,
                label="self-test hard-linked source",
            ),
            "ADR module hard link",
        )


def self_test() -> None:
    source = load_json(SOURCE)
    self_test_adr_byte_limits(source)
    self_test_json_fence_scanner()
    self_test_physical_source_paths()
    first = generated_bytes(build_registry(source))
    second = generated_bytes(build_registry(source))
    if first != second:
        raise AssertionError("decision registry generation is not deterministic")
    must_fail(
        lambda: load_json_bytes(b'{"subject":1,"subject":2}', "duplicate.json"),
        "duplicate source JSON key",
    )
    must_fail(
        lambda: load_json_bytes(b'{"bytes":NaN}', "nonfinite.json"),
        "non-finite source JSON number",
    )
    must_fail(
        lambda: load_json_bytes(b'{"bytes":1e9999}', "overflow.json"),
        "overflowing source JSON number",
    )
    must_fail(
        lambda: load_json_bytes(
            b'{"nested":' + b"[" * 33 + b"0" + b"]" * 33 + b"}",
            "depth.json",
        ),
        "source JSON root-depth limit plus one",
    )
    must_fail(
        lambda: parse_json_fence(
            '{"value":1e9999}',
            label="hostile Markdown JSON fence",
            limits=ADR_FENCE_JSON_LIMITS,
        ),
        "overflowing Markdown JSON fence number",
    )
    if (
        apply_single_semantic_mutation(
            {"value": 1},
            {"target": "DOCUMENT", "op": [], "path": "/value"},
        )
        is not None
    ):
        raise AssertionError("non-string semantic mutation operation was accepted")
    must_fail(
        lambda: parse_packet_subjects(
            (
                "```json\n"
                + json.dumps({"schema": REVIEW_PACKET_LIFECYCLE_SCHEMA, "state": []})
                + "\n```\n"
            ).encode("utf-8")
        ),
        "review packet with a non-string lifecycle state",
    )
    must_fail(
        lambda: relative_path("evidence//ambiguous.json", "evidence.path"),
        "non-canonical retained-evidence path",
    )
    must_fail(
        lambda: relative_path("\ud800.md", "source.path"),
        "non-scalar Unicode source path",
    )
    must_fail(
        lambda: validate_identity("urn:ncp:reviewer:\x07", "reviewer.identity"),
        "control character in reviewer identity",
    )
    must_fail(
        lambda: validate_https_url(
            "https://reviews.example.test/\x07receipt", "receipt.url"
        ),
        "control character in external receipt URL",
    )
    prior_git_parameters = os.environ.get("GIT_CONFIG_PARAMETERS")
    os.environ["GIT_CONFIG_PARAMETERS"] = "'core.replaceRefs=true'"
    try:
        if "GIT_CONFIG_PARAMETERS" in git_environment():
            raise AssertionError("git environment retained injected config parameters")
    finally:
        if prior_git_parameters is None:
            os.environ.pop("GIT_CONFIG_PARAMETERS", None)
        else:
            os.environ["GIT_CONFIG_PARAMETERS"] = prior_git_parameters

    base = build_registry(source)
    validate_decision_registry_instance(base)
    if (
        any(decision["status"] == "ACCEPTED" for decision in base["decisions"])
        or base["review_records"]
    ):
        raise AssertionError("empty review source produced optimistic acceptance")
    if base["semantic_closure_evaluation"]["state"] != "CLOSED":
        raise AssertionError("complete local semantic closure did not close")
    review_blocker_codes = {
        "MISSING_ROLE_ACCEPTANCE",
        "ACTIVE_REJECT",
        "UNRESOLVED_CONDITION",
        "INDEPENDENCE_NOT_ESTABLISHED",
    }
    for decision in base["decisions"]:
        blockers = decision["acceptance_blockers"]
        first_review = next(
            (
                index
                for index, blocker in enumerate(blockers)
                if blocker["code"] in review_blocker_codes
            ),
            len(blockers),
        )
        if any(
            blocker["code"] not in review_blocker_codes
            for blocker in blockers[first_review:]
        ):
            raise AssertionError("semantic-closure blocker followed a review blocker")

    closure_source = load_json(CLOSURE_SOURCE)

    def must_fail_closure_schema(instance: dict[str, Any], description: str) -> None:
        try:
            validate_instance(
                load_json(CLOSURE_SCHEMA),
                instance,
                f"self-test {description}",
                expected_schema_id=DECISION_CLOSURE_SCHEMA_ID,
            )
        except EvidenceSchemaError:
            return
        raise AssertionError(f"hostile closure schema self-test passed: {description}")

    malformed_schema_closure = copy.deepcopy(closure_source)
    malformed_schema_closure["decisions"][0] = {
        "id": "ADR-001",
        "questions": [{"question_id": "ADR-001-Q01"}],
    }
    must_fail_closure_schema(
        malformed_schema_closure,
        "truncated decision prefix member",
    )
    malformed_schema_closure = copy.deepcopy(closure_source)
    del malformed_schema_closure["decisions"][1]["questions"][0]["statement"]
    must_fail_closure_schema(
        malformed_schema_closure,
        "question prefix member missing a required field",
    )
    malformed_schema_closure = copy.deepcopy(closure_source)
    del malformed_schema_closure["decisions"][1]["questions"][0]["b03_deferral"][
        "parameters"
    ][0]["maximum"]
    must_fail_closure_schema(
        malformed_schema_closure,
        "parameter prefix member missing its maximum",
    )
    malformed_schema_closure = copy.deepcopy(closure_source)
    malformed_schema_closure["decisions"][1]["questions"][0]["b03_deferral"][
        "parameters"
    ][0]["unexpected"] = True
    must_fail_closure_schema(
        malformed_schema_closure,
        "parameter prefix member with an extra field",
    )
    malformed_schema_closure = copy.deepcopy(closure_source)
    malformed_deferral = malformed_schema_closure["decisions"][1]["questions"][0][
        "b03_deferral"
    ]
    malformed_deferral["identity_eligibility_universes"][0][
        "eligible_identities_sha256"
    ] = "0" * 64
    must_fail_closure_schema(
        malformed_schema_closure,
        "source-predicate identity envelope with a spurious universe digest",
    )
    malformed_closure = copy.deepcopy(closure_source)
    malformed_closure["unexpected_authority"] = True
    must_fail(
        lambda: build_registry(source, closure_source_override=malformed_closure),
        "malformed semantic closure with an unknown authority member",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["decisions"].pop()
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "missing ADR semantic closure",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["decisions"][0]["id"] = []
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "semantic closure with a non-string ADR ID",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["decisions"][0]["adr_source_set_sha256"] = "0" * 64
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "stale ADR semantic closure binding",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["semantic_example_contract"]["positive_authority"] = (
        "PRODUCTION_ADMISSION"
    )
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "semantic example contract with optimistic authority",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["semantic_example_contract"]["engine_requirement"] = (
        "ONE_ENGINE_IS_ENOUGH"
    )
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "semantic example contract with weakened engine parity",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["excluded_no_edge_components"][0][
        "prohibited_review_role_ids"
    ].append("protocol-reviewer")
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "no-edge component role overlapping a required review role",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["excluded_no_edge_components"][0]["prohibited_edge_classes"].pop()
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "no-edge component with an incomplete prohibited edge-class inventory",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_edge_classes = hostile_closure["excluded_no_edge_components"][0][
        "prohibited_edge_classes"
    ]
    hostile_edge_classes[0], hostile_edge_classes[1] = (
        hostile_edge_classes[1],
        hostile_edge_classes[0],
    )
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "schema-valid no-edge taxonomy with substituted ASCII order",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["decisions"][2]["questions"][0]["question_anchor"] = (
        "docs/adr/0003-authenticated-production-ingress.md#unknown-question"
    )
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "semantic question with an unknown ADR anchor",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["decisions"][6]["questions"].pop(0)
    hostile_closure["decisions"][6]["questions"][0]["question_id"] = "ADR-007-Q01"
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "deleted and renumbered semantic question",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["decisions"][1]["questions"][0]["b03_deferral"]["parameters"][0][
        "minimum"
    ] = None
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "VALIDATED B03 deferral with a missing literal bound",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["decisions"][1]["questions"][0]["b03_deferral"][
        "validation_state"
    ] = []
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "B03 deferral with a non-string validation state",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["decisions"][1]["questions"][0]["b03_deferral"]["parameters"][0][
        "required_tests"
    ] = [f"ADR-002-B03-FAKE-{index}" for index in range(1, 9)]
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "B03 deferral with fabricated test identities",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_deferral = hostile_closure["decisions"][4]["questions"][0]["b03_deferral"]
    hostile_parameter = hostile_deferral["parameters"][1]
    hostile_parameter["minimum"] = 0
    hostile_parameter["maximum"] = 0
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "vacuous zero-bound VALIDATED bounded-integer parameter",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_deferral = hostile_closure["decisions"][1]["questions"][0]["b03_deferral"]
    hostile_deferral["validation_state"] = "VALIDATED"
    hostile_parameter = hostile_deferral["parameters"][0]
    hostile_parameter["minimum"] = 2
    hostile_parameter["maximum"] = 1
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "B03 deferral with an inverted finite envelope",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["decisions"][1]["questions"][0]["b03_deferral"]["parameters"][0][
        "selected_value"
    ] = 1
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "future B03 selected value inside the B01 decision-set source",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_parameter = hostile_closure["decisions"][1]["questions"][0]["b03_deferral"][
        "parameters"
    ][0]
    hostile_parameter["selection_predicate_id"] = "ADR-002-B03-FAKE-PREDICATE"
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "B03 deferral with a substituted selection predicate",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["excluded_no_edge_components"][0]["canonical_aliases"] = [
        "cortexel"
    ]
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "global no-edge component missing a canonical repository alias",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["decisions"][4]["questions"][0]["b03_deferral"]["parameters"].pop()
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "B03 deferral with an omitted semantic parameter dimension",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_deferral = hostile_closure["decisions"][1]["questions"][0]["b03_deferral"]
    hostile_deferral["validation_state"] = "VALIDATED"
    hostile_parameter = hostile_deferral["parameters"][0]
    hostile_parameter["minimum"] = 1
    hostile_parameter["maximum"] = 2
    eligibility_universe = hostile_deferral["identity_eligibility_universes"][0]
    eligible_identities = [
        "contract/planes.v1.json",
        "proto/ncp.proto",
    ]
    eligibility_universe["eligible_identities"] = eligible_identities
    eligibility_universe["eligible_identities_sha256"] = b03_eligibility_set_sha256(
        "ADR-002-Q01",
        "STABLE_CORE_FILE_IDENTITIES",
        eligible_identities,
    )
    validated_envelope = build_registry(
        source,
        closure_source_override=hostile_closure,
    )
    if any(
        blocker["code"] == "INVALID_B03_DEFERRAL"
        for blocker in validated_envelope["decisions"][1]["acceptance_blockers"]
    ):
        raise AssertionError("valid finite B03 deferral envelope remained invalid")
    hostile_eligibility = copy.deepcopy(hostile_closure)
    hostile_eligibility["decisions"][1]["questions"][0]["b03_deferral"]["parameters"][
        0
    ]["maximum"] = 3
    must_fail(
        lambda: build_registry(
            source,
            closure_source_override=hostile_eligibility,
        ),
        "identity-set envelope wider than its exact eligibility universe",
    )
    for mutate_eligibility, label in (
        (
            lambda universe: universe.update({"eligible_identities_sha256": "0" * 64}),
            "B03 eligibility universe with a substituted context digest",
        ),
        (
            lambda universe: universe["eligible_identities"].reverse(),
            "B03 eligibility universe with noncanonical identity order",
        ),
        (
            lambda universe: universe["eligible_identities"].append(
                universe["eligible_identities"][-1]
            ),
            "B03 eligibility universe with a duplicate identity",
        ),
        (
            lambda universe: universe["eligible_identities"].append(
                "git@github.com:sepahead/Cortexel.git"
            ),
            "B03 eligibility universe containing a Cortexel alias token",
        ),
    ):
        hostile_eligibility = copy.deepcopy(hostile_closure)
        mutate_eligibility(
            hostile_eligibility["decisions"][1]["questions"][0]["b03_deferral"][
                "identity_eligibility_universes"
            ][0]
        )
        must_fail(
            lambda hostile_eligibility=hostile_eligibility: build_registry(
                source,
                closure_source_override=hostile_eligibility,
            ),
            label,
        )
    hostile_eligibility = copy.deepcopy(hostile_closure)
    hostile_eligibility["decisions"][1]["questions"][0]["b03_deferral"][
        "identity_eligibility_universes"
    ].clear()
    must_fail(
        lambda: build_registry(
            source,
            closure_source_override=hostile_eligibility,
        ),
        "validated identity-set envelope without an eligibility universe",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["decisions"][3]["example_requirements"]["required_case_ids"].clear()
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "ADR source set without a required semantic case",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["decisions"][0]["example_requirements"]["required_case_ids"][0] = (
        "adr002.realm-bound-contract-identity.v1"
    )
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "ADR semantic requirement bound to another ADR case",
    )
    if (
        apply_single_semantic_mutation(
            {"bounded": {"minimum": 0, "maximum": 1}},
            {"target": "DOCUMENT", "op": "REMOVE", "path": "/bounded"},
        )
        != {}
    ):
        raise AssertionError("one bounded structured mutation did not apply")
    if apply_single_semantic_mutation(
        {"a/bc": 1, "a/c": 2},
        {
            "target": "DOCUMENT",
            "op": "REPLACE",
            "path": "/a~1bc",
            "value": 3,
        },
    ) != {"a/bc": 3, "a/c": 2}:
        raise AssertionError("JSON Pointer escape consumed a suffix byte")
    if (
        apply_single_semantic_mutation(
            {"bounded": {"minimum": 0, "maximum": 1}},
            {"target": "DOCUMENT", "op": "REMOVE", "path": "/missing"},
        )
        is not None
    ):
        raise AssertionError("one mutation accepted a missing target")

    deep_parent: dict[str, Any] = {}
    cursor = deep_parent
    for _ in range(20):
        cursor["x"] = {}
        cursor = cursor["x"]
    deep_value: dict[str, Any] = {}
    cursor = deep_value
    for _ in range(20):
        cursor["y"] = {}
        cursor = cursor["y"]
    if (
        apply_single_semantic_mutation(
            deep_parent,
            {
                "target": "DOCUMENT",
                "op": "ADD",
                "path": "/" + "/".join(["x"] * 20) + "/value",
                "value": deep_value,
            },
        )
        is not None
    ):
        raise AssertionError("one mutation exceeded the full-object depth bound")

    inconsistent_counts = copy.deepcopy(base)
    inconsistent_counts["counts"]["decisions"] = 10
    try:
        validate_decision_registry_instance(inconsistent_counts)
    except EvidenceSchemaError:
        pass
    else:
        raise AssertionError("output schema accepted inconsistent decision counts")
    module_source_set = base["decisions"][3]["source_set"]
    if (
        module_source_set["sources"][0]["sha256"]
        != base["decisions"][3]["content_sha256"]
        or module_source_set["sources"][1]["path"]
        != EXPECTED_MODULE_PATHS["ADR-004"][0]
    ):
        raise AssertionError("ADR-004 source set does not bind main and module bytes")
    hostile_source_set = copy.deepcopy(module_source_set)
    hostile_source_set["sha256"] = "0" * 64
    must_fail(
        lambda: validate_adr_source_set(
            hostile_source_set,
            "self_test.source_set",
            expected_decision_id="ADR-004",
        ),
        "ADR source-set digest substitution",
    )
    hostile_source_set = copy.deepcopy(module_source_set)
    hostile_source_set["sources"][1]["path"] = (
        "docs/adr/modules/adr-009-cross-store-producer-and-compromise-evidence.md"
    )
    hostile_source_set = adr_source_set("ADR-004", hostile_source_set["sources"])
    must_fail(
        lambda: validate_adr_source_set(
            hostile_source_set,
            "self_test.source_set",
            expected_decision_id="ADR-004",
        ),
        "foreign ADR module in a valid source-set digest",
    )
    hostile_source_set = copy.deepcopy(module_source_set)
    hostile_source_set["sources"][1]["path"] = (
        "docs/adr/modules/adr-004-nested/subject.md"
    )
    hostile_source_set = adr_source_set("ADR-004", hostile_source_set["sources"])
    must_fail(
        lambda: validate_adr_source_set(
            hostile_source_set,
            "self_test.source_set",
            expected_decision_id="ADR-004",
        ),
        "nested ADR module in a valid source-set digest",
    )

    hostile = copy.deepcopy(source)
    hostile["decisions"][0]["status"] = "ACCEPTED"
    must_fail(lambda: build_registry(hostile), "manual ACCEPTED source status")

    hostile = copy.deepcopy(source)
    hostile["claim_boundary"] = "This local file certifies release readiness."
    must_fail(lambda: build_registry(hostile), "optimistic source claim boundary")

    hostile = copy.deepcopy(source)
    hostile["decisions"][0]["path"] = "contract/decision-registry.v1.json"
    must_fail(lambda: build_registry(hostile), "proposed path inside contract/")

    hostile = copy.deepcopy(source)
    hostile["decisions"][0]["path"] = "docs/adr/0001-nested/subject.md"
    must_fail(lambda: build_registry(hostile), "nested ADR main path")

    hostile = copy.deepcopy(source)
    hostile["decisions"][0]["path"] = "docs/adr/0002-wrong-decision.md"
    must_fail(
        lambda: build_registry(hostile), "ADR main path with the wrong decision id"
    )

    hostile = copy.deepcopy(source)
    hostile["decisions"][0]["module_paths"] = list(EXPECTED_MODULE_PATHS["ADR-004"])
    must_fail(lambda: build_registry(hostile), "module on an unallocated ADR")

    hostile = copy.deepcopy(source)
    hostile["decisions"][3]["module_paths"] = []
    must_fail(lambda: build_registry(hostile), "missing closed ADR-004 module")

    hostile = copy.deepcopy(source)
    hostile["decisions"][0]["required_reviews"] *= 2
    must_fail(lambda: build_registry(hostile), "duplicate reviewer roles")

    hostile = copy.deepcopy(source)
    hostile["decisions"][1]["defect_ids"].remove("D19")
    must_fail(lambda: build_registry(hostile), "missing D19 coverage")

    hostile = copy.deepcopy(source)
    hostile["decisions"][3]["defect_ids"].remove("D20")
    hostile["decisions"][8]["defect_ids"].remove("D20")
    must_fail(lambda: build_registry(hostile), "missing D20 coverage")

    hostile = copy.deepcopy(source)
    hostile["decisions"][10]["defect_ids"].append("D21")
    must_fail(lambda: build_registry(hostile), "unknown D21 defect")

    hostile = copy.deepcopy(source)
    hostile["decisions"][10]["defect_ids"][0] = {}
    must_fail(lambda: build_registry(hostile), "non-string defect identifier")

    decision = copy.deepcopy(source["decisions"][0])
    original = (ROOT / decision["path"]).read_bytes()
    damaged = original.replace(b"## Formal properties", b"## Missing properties", 1)
    must_fail(
        lambda: validate_markdown(decision, content_override=damaged),
        "missing mandatory ADR section",
    )
    damaged = original + b"\n## Formal properties\n\nDuplicate hostile heading.\n"
    must_fail(
        lambda: validate_markdown(decision, content_override=damaged),
        "duplicate mandatory ADR heading",
    )
    damaged = original.replace(INVARIANT_STATUS.encode(), b"- Status: `ACCEPTED`", 1)
    must_fail(
        lambda: validate_markdown(decision, content_override=damaged),
        "mutable ADR status metadata",
    )
    damaged = original.replace(
        INVARIANT_NORMATIVE_EFFECT.encode(),
        b"- Normative effect while proposed: none",
        1,
    )
    must_fail(
        lambda: validate_markdown(decision, content_override=damaged),
        "status-dependent ADR normative-effect metadata",
    )
    damaged = original + b'\n```json\n{"nonfinite":NaN}\n```\n'
    must_fail(
        lambda: validate_markdown(decision, content_override=damaged),
        "non-finite ADR JSON example",
    )
    content = b'{"self_test":"bounded review evidence"}\n'
    large_evidence = b"x" * MAX_EVIDENCE_BYTES
    aggregate_refs = [
        test_evidence_ref(f"aggregate-limit/{index}", large_evidence)
        for index in range(MAX_TOTAL_EVIDENCE_BYTES // MAX_EVIDENCE_BYTES + 1)
    ]
    aggregate_overrides = {
        reference["path"]: large_evidence for reference in aggregate_refs
    }

    def exceed_aggregate_evidence_limit() -> None:
        evidence_cache: dict[str, bytes] = {}
        for index, reference in enumerate(aggregate_refs):
            validate_evidence_ref(
                reference,
                f"self_test.aggregate_refs[{index}]",
                artifact_overrides=aggregate_overrides,
                evidence_cache=evidence_cache,
            )

    must_fail(
        exceed_aggregate_evidence_limit,
        "aggregate retained-evidence byte amplification",
    )

    current_packet_content = test_packet_content(base)
    review_base = build_registry(
        source,
        packet_override=current_packet_content,
        subject_resolver=test_subject_resolver,
    )
    if review_base["review_packet_subject"] is None:
        raise AssertionError(
            "zero-review CURRENT packet was not structurally validated"
        )
    emitted = emit_review_subject(
        "1" * 40,
        source=source,
        subject_resolver=test_subject_resolver,
    )
    if emitted != review_base["review_packet_subject"]:
        raise AssertionError("review-subject emitter differs from packet validation")

    def stale_committed_input_resolver(
        source_commit: str, repository_path: str
    ) -> tuple[str, bytes]:
        tree, content_at_commit = test_subject_resolver(source_commit, repository_path)
        if repository_path == GENERATOR:
            return tree, content_at_commit + b"\n# stale committed generator\n"
        return tree, content_at_commit

    must_fail(
        lambda: build_registry(
            source,
            packet_override=current_packet_content,
            subject_resolver=stale_committed_input_resolver,
        ),
        "CURRENT packet whose commit contains a stale generator",
    )

    def stale_committed_schema_resolver(
        source_commit: str, repository_path: str
    ) -> tuple[str, bytes]:
        tree, content_at_commit = test_subject_resolver(source_commit, repository_path)
        if repository_path == SCHEMA_RELATIVE:
            return tree, content_at_commit + b"\n"
        return tree, content_at_commit

    must_fail(
        lambda: build_registry(
            source,
            packet_override=current_packet_content,
            subject_resolver=stale_committed_schema_resolver,
        ),
        "CURRENT packet whose commit contains a stale output schema",
    )

    def stale_committed_closure_source_resolver(
        source_commit: str, repository_path: str
    ) -> tuple[str, bytes]:
        tree, content_at_commit = test_subject_resolver(source_commit, repository_path)
        if repository_path == CLOSURE_SOURCE_RELATIVE:
            return tree, content_at_commit + b"\n"
        return tree, content_at_commit

    must_fail(
        lambda: build_registry(
            source,
            packet_override=current_packet_content,
            subject_resolver=stale_committed_closure_source_resolver,
        ),
        "CURRENT packet whose commit contains a stale semantic-closure source",
    )

    def stale_committed_closure_schema_resolver(
        source_commit: str, repository_path: str
    ) -> tuple[str, bytes]:
        tree, content_at_commit = test_subject_resolver(source_commit, repository_path)
        if repository_path == CLOSURE_SCHEMA_RELATIVE:
            return tree, content_at_commit + b"\n"
        return tree, content_at_commit

    must_fail(
        lambda: build_registry(
            source,
            packet_override=current_packet_content,
            subject_resolver=stale_committed_closure_schema_resolver,
        ),
        "CURRENT packet whose commit contains a stale semantic-closure schema",
    )

    def stale_committed_module_resolver(
        source_commit: str, repository_path: str
    ) -> tuple[str, bytes]:
        tree, content_at_commit = test_subject_resolver(source_commit, repository_path)
        if repository_path == EXPECTED_MODULE_PATHS["ADR-004"][0]:
            return tree, content_at_commit + b"\n"
        return tree, content_at_commit

    must_fail(
        lambda: build_registry(
            source,
            packet_override=current_packet_content,
            subject_resolver=stale_committed_module_resolver,
        ),
        "CURRENT packet whose commit contains a stale ADR companion module",
    )

    def stale_committed_source_resolver(
        source_commit: str, repository_path: str
    ) -> tuple[str, bytes]:
        tree, content_at_commit = test_subject_resolver(source_commit, repository_path)
        if repository_path == SOURCE_RELATIVE:
            stale_source = copy.deepcopy(source)
            stale_source["decisions"][0]["required_reviews"][0]["label"] += " stale"
            return tree, source_bytes(stale_source)
        return tree, content_at_commit

    must_fail(
        lambda: build_registry(
            source,
            packet_override=current_packet_content,
            subject_resolver=stale_committed_source_resolver,
        ),
        "CURRENT packet whose commit contains stale role source",
    )
    must_fail(
        lambda: build_registry(
            source,
            packet_override=b"# packet without a machine lifecycle\n",
        ),
        "packet without a machine-readable lifecycle",
    )
    reviewed_source = copy.deepcopy(source)
    requirements = reviewed_source["decisions"][0]["required_reviews"]
    open_reviews = [
        test_review(
            review_id=f"adr001-{requirement['role_id']}-{identity_index}",
            adr_id="ADR-001",
            requirement=requirement,
            registry=review_base,
            content=content,
            identity_suffix=f"{requirement['role_id']}-{identity_index}",
        )
        for requirement in requirements
        for identity_index in range(requirement["min_distinct_identities"])
    ]
    current_corpus = load_json(ROOT / SEMANTIC_CORPUS_PATH)
    current_corpus["decision_set_binding"] = expected_corpus_decision_binding(
        base["decision_set"],
        json.dumps(
            decision_set_projection(
                base["decisions"],
                source,
                base["review_policy"],
                base["decision_set"]["semantic_closure"],
            ),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
    )
    current_corpus_bytes = source_bytes(current_corpus)

    hostile_diagnostic_registry = copy.deepcopy(current_corpus)
    hostile_diagnostic_registry["diagnostic_registry"][0] = {}
    must_fail(
        lambda: build_registry(
            source,
            closure_artifact_overrides={
                SEMANTIC_CORPUS_PATH: source_bytes(hostile_diagnostic_registry),
            },
            packet_override=current_packet_content,
        ),
        "semantic corpus with a non-string diagnostic-registry member",
    )

    hostile_case_order = copy.deepcopy(current_corpus)
    hostile_case_order["cases"][0], hostile_case_order["cases"][1] = (
        hostile_case_order["cases"][1],
        hostile_case_order["cases"][0],
    )
    must_fail(
        lambda: build_registry(
            source,
            closure_artifact_overrides={
                SEMANTIC_CORPUS_PATH: source_bytes(hostile_case_order),
            },
            subject_resolver=test_subject_resolver,
            packet_override=current_packet_content,
        ),
        "semantic corpus with shuffled case order",
    )

    hostile_case_diagnostics = copy.deepcopy(current_corpus)
    hostile_case_diagnostics["cases"][0]["expected_diagnostics"] = [{}]
    must_fail(
        lambda: build_registry(
            source,
            closure_artifact_overrides={
                SEMANTIC_CORPUS_PATH: source_bytes(hostile_case_diagnostics),
            },
            packet_override=current_packet_content,
        ),
        "semantic corpus case with a non-string expected diagnostic",
    )

    hostile_mutation_diagnostics = copy.deepcopy(current_corpus)
    hostile_mutation_diagnostics["cases"][0]["mutations"][0]["expected_diagnostics"] = [
        {}
    ]
    must_fail(
        lambda: build_registry(
            source,
            closure_artifact_overrides={
                SEMANTIC_CORPUS_PATH: source_bytes(hostile_mutation_diagnostics),
            },
            packet_override=current_packet_content,
        ),
        "semantic corpus mutation with a non-string expected diagnostic",
    )

    hostile_case_result = copy.deepcopy(current_corpus)
    hostile_case_result["cases"][0]["expected_profile_result"] = []
    must_fail(
        lambda: build_registry(
            source,
            closure_artifact_overrides={
                SEMANTIC_CORPUS_PATH: source_bytes(hostile_case_result),
            },
            packet_override=current_packet_content,
        ),
        "semantic corpus case with a non-string expected result",
    )

    hostile_case_scope = copy.deepcopy(current_corpus)
    hostile_case_scope["cases"][0]["scope"] = {}
    must_fail(
        lambda: build_registry(
            source,
            closure_artifact_overrides={
                SEMANTIC_CORPUS_PATH: source_bytes(hostile_case_scope),
            },
            packet_override=current_packet_content,
        ),
        "semantic corpus case with a non-string scope",
    )

    hostile_case_identity = copy.deepcopy(current_corpus)
    hostile_case_identity["cases"][0]["profile"] = hostile_case_identity["cases"][2][
        "profile"
    ]
    hostile_identity_registry = build_registry(
        source,
        closure_artifact_overrides={
            SEMANTIC_CORPUS_PATH: source_bytes(hostile_case_identity),
        },
        subject_resolver=test_subject_resolver,
        packet_override=current_packet_content,
    )
    if (
        hostile_identity_registry["semantic_closure_evaluation"]["semantic_corpus"][
            "observed_status"
        ]
        != "INCOMPLETE_COVERAGE"
    ):
        raise AssertionError("semantic corpus accepted an altered closed case identity")

    hostile_mutation_admission = copy.deepcopy(current_corpus)
    hostile_mutation_admission["cases"][0]["mutations"][0]["production_admission"] = []
    must_fail(
        lambda: build_registry(
            source,
            closure_artifact_overrides={
                SEMANTIC_CORPUS_PATH: source_bytes(hostile_mutation_admission),
            },
            packet_override=current_packet_content,
        ),
        "semantic corpus mutation with a non-string production admission",
    )

    reviewed_source["review_records"] = open_reviews
    reviewed = build_registry(
        reviewed_source,
        artifact_overrides=test_artifact_overrides(reviewed_source, content),
        closure_artifact_overrides={
            SEMANTIC_CORPUS_PATH: current_corpus_bytes,
        },
        subject_resolver=test_subject_resolver,
        packet_override=current_packet_content,
    )
    if reviewed["decisions"][0]["status"] != "ACCEPTED":
        raise AssertionError(
            "complete local closure and reviews did not accept subject"
        )
    if reviewed["decisions"][0]["acceptance_blockers"]:
        raise AssertionError("complete local closure and reviews retained a blocker")

    stale_corpus = copy.deepcopy(current_corpus)
    stale_corpus["decision_set_binding"]["sha256"] = "0" * 64
    semantic_open = build_registry(
        reviewed_source,
        artifact_overrides=test_artifact_overrides(reviewed_source, content),
        closure_artifact_overrides={
            SEMANTIC_CORPUS_PATH: source_bytes(stale_corpus),
        },
        subject_resolver=test_subject_resolver,
        packet_override=current_packet_content,
    )
    if (
        semantic_open["semantic_closure_evaluation"]["state"] != "OPEN"
        or semantic_open["decisions"][0]["status"] != "PROPOSED"
    ):
        raise AssertionError("stale semantic corpus did not block reviewed ADRs")

    accepted_source = reviewed_source
    reviews = open_reviews

    def build_test(
        test_source: dict[str, Any],
        *,
        test_policy_overrides: dict[str, bytes] | None = None,
        test_resolver: SubjectResolver = test_subject_resolver,
        test_packet: bytes = current_packet_content,
    ) -> dict[str, Any]:
        return build_registry(
            test_source,
            artifact_overrides=test_artifact_overrides(test_source, content),
            closure_artifact_overrides={
                SEMANTIC_CORPUS_PATH: current_corpus_bytes,
            },
            subject_resolver=test_resolver,
            policy_overrides=test_policy_overrides,
            packet_override=test_packet,
        )

    accepted = reviewed
    expected_override_source = source_bytes(accepted_source)
    if accepted["source"] != {
        "path": SOURCE_RELATIVE,
        "sha256": sha256_bytes(expected_override_source),
        "bytes": len(expected_override_source),
    }:
        raise AssertionError("source override identity does not bind override bytes")

    hostile = copy.deepcopy(accepted_source)
    hostile["review_records"][0]["adr_id"] = {}
    must_fail(lambda: build_test(hostile), "review with a non-string ADR ID")

    hostile = copy.deepcopy(accepted_source)
    hostile["review_records"][0]["reviewer"]["identity_kind"] = []
    must_fail(lambda: build_test(hostile), "review with a non-string identity kind")

    hostile = copy.deepcopy(accepted_source)
    hostile["review_records"][0]["decision"] = {}
    must_fail(lambda: build_test(hostile), "review with a non-string decision")

    hostile = copy.deepcopy(accepted_source)
    hostile["review_records"][1]["external_receipt"] = copy.deepcopy(
        hostile["review_records"][0]["external_receipt"]
    )
    must_fail(
        lambda: build_test(hostile),
        "distinct reviews reusing one external receipt",
    )

    template_registry = build_registry(
        source,
        packet_override=test_packet_content(base, state="TEMPLATE"),
    )
    if template_registry["review_packet_subject"] is not None:
        raise AssertionError("zero-review template packet produced a review subject")
    must_fail(
        lambda: build_test(
            accepted_source,
            test_packet=test_packet_content(base, state="TEMPLATE"),
        ),
        "review records against a packet template",
    )
    must_fail(
        lambda: build_test(
            accepted_source,
            test_packet=test_packet_content(base, state="SUPERSEDED"),
        ),
        "review records against a machine-superseded packet",
    )

    mismatched_packet_block = packet_subject_projection(
        review_base["decisions"],
        review_base["decision_set"],
        review_base["review_policy"],
        source_commit="1" * 40,
        source_tree="2" * 40,
        committed_source_identity=test_decision_source_identity(),
    )
    mismatched_packet_block["decision_set"] = copy.deepcopy(
        mismatched_packet_block["decision_set"]
    )
    mismatched_packet_block["decision_set"]["sha256"] = "0" * 64
    must_fail(
        lambda: build_test(
            accepted_source,
            test_packet=test_packet_content(
                review_base, block_override=mismatched_packet_block
            ),
        ),
        "packet block with a mismatched decision set",
    )
    must_fail(
        lambda: build_registry(
            source,
            packet_override=test_packet_content(
                review_base, block_override=mismatched_packet_block
            ),
            subject_resolver=test_subject_resolver,
        ),
        "zero-review CURRENT packet with a mismatched decision set",
    )
    must_fail(
        lambda: build_test(
            accepted_source,
            test_packet=current_packet_content
            + current_packet_content[current_packet_content.index(b"```json") :],
        ),
        "packet with duplicate CURRENT review-subject blocks",
    )

    self_digest_packet_block = packet_subject_projection(
        review_base["decisions"],
        review_base["decision_set"],
        review_base["review_policy"],
        source_commit="1" * 40,
        source_tree="2" * 40,
        committed_source_identity=test_decision_source_identity(),
    )
    self_digest_packet_block["review_packet_sha256"] = "0" * 64
    must_fail(
        lambda: build_test(
            accepted_source,
            test_packet=test_packet_content(
                review_base, block_override=self_digest_packet_block
            ),
        ),
        "packet block that embeds a self-referential digest",
    )

    stale = copy.deepcopy(accepted_source)
    historical_adr = (
        ROOT / accepted_source["decisions"][0]["path"]
    ).read_bytes() + b"\n"
    stale_subject = stale["review_records"][0]["subject"]
    stale_subject["adr_content_sha256"] = sha256_bytes(historical_adr)
    stale_subject["adr_bytes"] = len(historical_adr)
    historical_sources = copy.deepcopy(stale_subject["adr_source_set"]["sources"])
    historical_sources[0]["sha256"] = sha256_bytes(historical_adr)
    historical_sources[0]["bytes"] = len(historical_adr)
    stale_subject["adr_source_set"] = adr_source_set("ADR-001", historical_sources)
    stale_subject["source_commit"] = "3" * 40
    stale_subject["source_tree"] = "3" * 40
    stale_subject["review_packet_sha256"] = "e" * 64

    def historical_resolver(source_commit: str, adr_path: str) -> tuple[str, bytes]:
        if source_commit == "3" * 40:
            return "3" * 40, historical_adr
        return test_subject_resolver(source_commit, adr_path)

    stale_registry = build_test(stale, test_resolver=historical_resolver)
    if (
        stale_registry["decisions"][0]["status"] != "PROPOSED"
        or sum(
            not record["derived"]["current_subject"]
            for record in stale_registry["review_records"]
        )
        != 1
    ):
        raise AssertionError("stale review was not retained and excluded")

    module_review_source = copy.deepcopy(source)
    module_requirement = module_review_source["decisions"][3]["required_reviews"][0]
    module_review = test_review(
        review_id="adr004-module-source-set-review",
        adr_id="ADR-004",
        requirement=module_requirement,
        registry=review_base,
        content=content,
        identity_suffix="adr004-module-source-set",
    )
    historical_module = (
        ROOT / EXPECTED_MODULE_PATHS["ADR-004"][0]
    ).read_bytes() + b"\n"
    module_sources = copy.deepcopy(
        module_review["subject"]["adr_source_set"]["sources"]
    )
    module_sources[1]["sha256"] = sha256_bytes(historical_module)
    module_sources[1]["bytes"] = len(historical_module)
    module_review["subject"]["adr_source_set"] = adr_source_set(
        "ADR-004", module_sources
    )
    module_review["subject"]["source_commit"] = "3" * 40
    module_review["subject"]["source_tree"] = "3" * 40
    module_review["subject"]["review_packet_sha256"] = "e" * 64
    module_review_source["review_records"] = [module_review]

    def historical_module_resolver(
        source_commit: str, repository_path: str
    ) -> tuple[str, bytes]:
        if source_commit == "3" * 40:
            if repository_path == EXPECTED_MODULE_PATHS["ADR-004"][0]:
                return "3" * 40, historical_module
            return "3" * 40, (ROOT / repository_path).read_bytes()
        return test_subject_resolver(source_commit, repository_path)

    module_stale_registry = build_test(
        module_review_source,
        test_resolver=historical_module_resolver,
    )
    if (
        sum(
            not record["derived"]["current_subject"]
            for record in module_stale_registry["review_records"]
        )
        != 1
        or "ADR_SOURCE_SET_DIGEST_MISMATCH"
        not in module_stale_registry["review_records"][0]["derived"]["stale_reasons"]
    ):
        raise AssertionError("stale companion-module review was not excluded")

    packet_stale = copy.deepcopy(accepted_source)
    packet_stale["review_records"][0]["subject"]["review_packet_sha256"] = "0" * 64
    packet_stale_registry = build_test(packet_stale)
    if (
        packet_stale_registry["decisions"][0]["status"] != "PROPOSED"
        or sum(
            not record["derived"]["current_subject"]
            for record in packet_stale_registry["review_records"]
        )
        != 1
    ):
        raise AssertionError("stale review-packet identity was not excluded")

    policy_override = {GENERATOR: b"weakened generator policy\n"}
    policy_changed_base = build_registry(
        source,
        policy_overrides=policy_override,
        packet_override=test_packet_content(base, state="TEMPLATE"),
    )
    policy_changed_packet = test_packet_content(policy_changed_base)

    def policy_changed_resolver(
        source_commit: str, repository_path: str
    ) -> tuple[str, bytes]:
        tree, content_at_commit = test_subject_resolver(source_commit, repository_path)
        return tree, policy_override.get(repository_path, content_at_commit)

    policy_stale_registry = build_test(
        accepted_source,
        test_policy_overrides=policy_override,
        test_resolver=policy_changed_resolver,
        test_packet=policy_changed_packet,
    )
    if policy_stale_registry["decisions"][0]["status"] != "PROPOSED" or sum(
        not record["derived"]["current_subject"]
        for record in policy_stale_registry["review_records"]
    ) != len(reviews):
        raise AssertionError("review-policy change did not stale prior reviews")

    rejecting = copy.deepcopy(accepted_source)
    rejecting["review_records"][0]["decision"] = "REJECT"
    rejected = build_test(rejecting)
    if "ACTIVE_REJECT" not in {
        blocker["code"] for blocker in rejected["decisions"][0]["acceptance_blockers"]
    }:
        raise AssertionError("active rejection did not block acceptance")

    conditional = copy.deepcopy(accepted_source)
    conditional_review = conditional["review_records"][0]
    conditional_review["decision"] = "ACCEPT_WITH_CONDITIONS"
    conditional_review["conditions"] = [
        {
            "condition_id": "CONDITION-1",
            "statement": "Retain exact same-subject resolution evidence.",
            "status": "OPEN",
            "resolution_evidence": [],
            "closure": None,
        }
    ]
    unresolved = build_test(conditional)
    if "UNRESOLVED_CONDITION" not in {
        blocker["code"] for blocker in unresolved["decisions"][0]["acceptance_blockers"]
    }:
        raise AssertionError("unresolved condition did not block acceptance")

    hostile = copy.deepcopy(conditional)
    hostile["review_records"][0]["conditions"][0]["status"] = []
    must_fail(lambda: build_test(hostile), "condition with a non-string status")

    resolved = copy.deepcopy(conditional)
    resolved_review = resolved["review_records"][0]
    resolved_condition = resolved_review["conditions"][0]
    resolved_condition["status"] = "RESOLVED"
    resolved_condition["resolution_evidence"] = [
        test_evidence_ref("condition-1/resolution", content)
    ]
    resolved_condition["closure"] = {
        "reviewer_identity": resolved_review["reviewer"]["identity"],
        "decision_set_sha256": resolved_review["subject"]["decision_set_sha256"],
        "adr_content_sha256": resolved_review["subject"]["adr_content_sha256"],
        "adr_source_set_sha256": resolved_review["subject"]["adr_source_set"]["sha256"],
        "timestamp_utc": "2026-07-26T12:01:00Z",
        "external_receipt": test_evidence_ref("condition-1/closure", content),
    }
    resolved_registry = build_test(resolved)
    if "UNRESOLVED_CONDITION" in {
        blocker["code"]
        for blocker in resolved_registry["decisions"][0]["acceptance_blockers"]
    }:
        raise AssertionError("same-reviewer resolved condition did not count")

    hostile = copy.deepcopy(resolved)
    hostile_review = hostile["review_records"][0]
    hostile_review["conditions"][0]["closure"]["timestamp_utc"] = hostile_review[
        "timestamp_utc"
    ]
    must_fail(
        lambda: build_test(hostile),
        "condition closure without strictly later causal time",
    )

    hostile = copy.deepcopy(resolved)
    hostile["review_records"][0]["conditions"][0]["closure"]["reviewer_identity"] = (
        "urn:ncp:test-reviewer:different"
    )
    must_fail(
        lambda: build_test(hostile),
        "condition closed by a different identity",
    )

    hostile = copy.deepcopy(resolved)
    hostile_condition = hostile["review_records"][0]["conditions"][0]
    hostile_condition["closure"]["external_receipt"] = copy.deepcopy(
        hostile["review_records"][0]["role_authorization"]
    )
    must_fail(
        lambda: build_test(hostile),
        "condition closure reused role-authorization evidence",
    )

    hostile = copy.deepcopy(resolved)
    hostile_condition = hostile["review_records"][0]["conditions"][0]
    hostile_condition["resolution_evidence"] = [
        copy.deepcopy(hostile["review_records"][0]["external_receipt"])
    ]
    must_fail(
        lambda: build_test(hostile),
        "condition resolution reused review evidence",
    )

    hostile = copy.deepcopy(resolved)
    hostile_condition = hostile["review_records"][0]["conditions"][0]
    hostile_condition["resolution_evidence"] *= 2
    must_fail(
        lambda: build_test(hostile),
        "condition resolution duplicated one retained evidence path",
    )

    independent_index = next(
        index
        for index, review in enumerate(reviews)
        if next(
            requirement
            for requirement in requirements
            if requirement["role_id"] == review["role_id"]
        )["requires_independence"]
    )
    hostile = copy.deepcopy(accepted_source)
    independent_review = hostile["review_records"][independent_index]
    independent_review["reviewer"]["implementation_owner_identities"] = [
        independent_review["reviewer"]["identity"]
    ]
    must_fail(
        lambda: build_test(hostile),
        "self-review asserted as independent",
    )

    hostile = copy.deepcopy(accepted_source)
    hostile["review_records"][independent_index]["reviewer"][
        "implementation_owner_identities"
    ] = [{}]
    must_fail(
        lambda: build_test(hostile),
        "review with a non-string implementation-owner identity",
    )

    hostile = copy.deepcopy(accepted_source)
    hostile["review_records"][independent_index]["independence_assessment"] = None
    must_fail(
        lambda: build_test(hostile),
        "independence claim without a retained assessment",
    )

    unqualified = copy.deepcopy(accepted_source)
    unqualified_review = unqualified["review_records"][independent_index]
    unqualified_review["reviewer"]["independence_claimed"] = False
    unqualified_review["independence_assessment"] = None
    unqualified_registry = build_test(unqualified)
    if "INDEPENDENCE_NOT_ESTABLISHED" not in {
        blocker["code"]
        for blocker in unqualified_registry["decisions"][0]["acceptance_blockers"]
    }:
        raise AssertionError("unestablished independence counted as acceptance")

    hostile = copy.deepcopy(accepted_source)
    hostile["review_records"][independent_index]["independence_assessment"][
        "sha256"
    ] = "0" * 64
    must_fail(
        lambda: build_test(hostile),
        "independence-assessment digest mismatch",
    )

    hostile = copy.deepcopy(accepted_source)
    hostile_review = hostile["review_records"][independent_index]
    hostile_review["independence_assessment"] = copy.deepcopy(
        hostile_review["external_receipt"]
    )
    must_fail(
        lambda: build_test(hostile),
        "independence assessment reused the review receipt",
    )

    hostile = copy.deepcopy(accepted_source)
    hostile["review_records"][0]["subject"]["source_commit"] = "4" * 40
    must_fail(lambda: build_test(hostile), "unresolvable source commit")

    hostile = copy.deepcopy(accepted_source)
    hostile["review_records"][0]["subject"]["source_tree"] = "4" * 40
    must_fail(lambda: build_test(hostile), "mismatched source tree")

    hostile = copy.deepcopy(accepted_source)
    hostile["review_records"][0]["subject"]["adr_content_sha256"] = "0" * 64
    must_fail(lambda: build_test(hostile), "mismatched source ADR blob digest")

    hostile = copy.deepcopy(accepted_source)
    hostile["review_records"][0]["subject"]["adr_source_set"]["sha256"] = "0" * 64
    must_fail(lambda: build_test(hostile), "mismatched ADR source-set digest")

    hostile = copy.deepcopy(accepted_source)
    hostile["review_records"][0]["subject"]["adr_bytes"] += 1
    must_fail(lambda: build_test(hostile), "mismatched source ADR blob byte length")

    hostile = copy.deepcopy(accepted_source)
    hostile["review_records"][0]["external_receipt"]["url"] = (
        "http://reviews.example.test/untrusted"
    )
    must_fail(
        lambda: build_test(hostile),
        "non-HTTPS review receipt",
    )

    hostile = copy.deepcopy(accepted_source)
    hostile["review_records"][0]["external_receipt"]["url"] = "https://127.0.0.1/review"
    must_fail(
        lambda: build_test(hostile),
        "IP-literal review receipt host",
    )

    hostile = copy.deepcopy(accepted_source)
    hostile["review_records"][0]["external_receipt"]["url"] = (
        "https://bad..example.test/review"
    )
    must_fail(
        lambda: build_test(hostile),
        "non-canonical review receipt DNS name",
    )

    hostile = copy.deepcopy(accepted_source)
    hostile["review_records"][0]["external_receipt"]["sha256"] = "0" * 64
    must_fail(
        lambda: build_test(hostile),
        "review receipt digest mismatch",
    )

    hostile = copy.deepcopy(accepted_source)
    hostile["review_records"][0]["role_authorization"] = copy.deepcopy(
        hostile["review_records"][0]["external_receipt"]
    )
    must_fail(
        lambda: build_test(hostile),
        "role authorization reused the review receipt",
    )

    hostile = copy.deepcopy(accepted_source)
    predecessor = hostile["review_records"][0]
    nonmonotonic_successor = copy.deepcopy(predecessor)
    nonmonotonic_successor["review_id"] = "adr001-nonmonotonic-successor"
    nonmonotonic_successor["supersedes"] = predecessor["review_id"]
    nonmonotonic_successor["timestamp_utc"] = "2026-07-26T11:59:59Z"
    hostile["review_records"].append(nonmonotonic_successor)
    must_fail(
        lambda: build_test(hostile),
        "nonmonotonic review supersession timestamp",
    )

    hostile = copy.deepcopy(accepted_source)
    original_review = hostile["review_records"][0]
    successor_one = copy.deepcopy(original_review)
    successor_one["review_id"] = "adr001-fork-successor-one"
    successor_one["supersedes"] = original_review["review_id"]
    successor_one["timestamp_utc"] = "2026-07-26T12:01:00Z"
    successor_two = copy.deepcopy(original_review)
    successor_two["review_id"] = "adr001-fork-successor-two"
    successor_two["supersedes"] = original_review["review_id"]
    successor_two["timestamp_utc"] = "2026-07-26T12:01:00Z"
    hostile["review_records"].extend([successor_one, successor_two])
    must_fail(
        lambda: build_test(hostile),
        "review supersession fork",
    )

    hostile = copy.deepcopy(accepted_source)
    first_review = hostile["review_records"][0]
    cycle_a = copy.deepcopy(first_review)
    cycle_b = copy.deepcopy(first_review)
    cycle_a["review_id"] = "adr001-cycle-a"
    cycle_a["supersedes"] = "adr001-cycle-b"
    cycle_b["review_id"] = "adr001-cycle-b"
    cycle_b["supersedes"] = "adr001-cycle-a"
    hostile["review_records"] = hostile["review_records"][1:] + [cycle_a, cycle_b]
    must_fail(
        lambda: build_test(hostile),
        "review supersession cycle",
    )


def require_all_accepted(registry: dict[str, Any]) -> None:
    blocked = [
        decision
        for decision in registry["decisions"]
        if decision["status"] != "ACCEPTED"
    ]
    if not blocked:
        return
    summary = "; ".join(
        f"{decision['id']}="
        + ",".join(
            sorted({blocker["code"] for blocker in decision["acceptance_blockers"]})
        )
        for decision in blocked
    )
    fail(f"all ADRs are not structurally accepted: {summary}")


def emit_review_subject(
    source_commit: str,
    *,
    source: dict[str, Any] | None = None,
    subject_resolver: SubjectResolver = resolve_git_subject,
    policy_overrides: dict[str, bytes] | None = None,
    closure_source_override: dict[str, Any] | None = None,
    closure_schema_override: bytes | None = None,
) -> dict[str, Any]:
    commit = validate_hex(source_commit, HEX40, "review source commit")
    value = copy.deepcopy(source if source is not None else load_json(SOURCE))
    decisions, review_records = validate_source(value)
    if review_records:
        fail("review-subject emission requires a zero-review decision source")
    generated = generated_decisions(decisions)
    current_policy = review_policy(policy_overrides)
    closure_requirements = load_closure_requirements(
        generated,
        source_override=closure_source_override,
        schema_override=closure_schema_override,
    )
    current_set = decision_set(
        generated,
        value,
        current_policy,
        closure_requirements["binding"],
    )
    source_tree, _ = subject_resolver(commit, SOURCE_RELATIVE)
    validate_hex(source_tree, HEX40, "resolved review source tree")
    committed_source_identity = validate_committed_review_inputs(
        commit,
        source_tree,
        generated,
        value,
        current_policy,
        closure_requirements["binding"],
        subject_resolver=subject_resolver,
    )
    return packet_subject_projection(
        generated,
        current_set,
        current_policy,
        source_commit=commit,
        source_tree=source_tree,
        committed_source_identity=committed_source_identity,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write", action="store_true", help="replace the generated proposed registry"
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="check the generated proposed registry (the default)",
    )
    mode.add_argument(
        "--emit-review-subject",
        metavar="COMMIT",
        help=(
            "emit a CURRENT review-subject JSON block only when COMMIT contains "
            "the exact zero-review source, generator, schemas, semantic-closure "
            "source, and ADR bytes"
        ),
    )
    parser.add_argument(
        "--self-test", action="store_true", help="also run hostile review mutations"
    )
    parser.add_argument(
        "--require-all-accepted",
        action="store_true",
        help="fail unless all eleven ADRs have complete current review obligations",
    )
    args = parser.parse_args()

    try:
        if args.self_test:
            self_test()
        if args.emit_review_subject is not None:
            subject = emit_review_subject(args.emit_review_subject)
            print(json.dumps(subject, ensure_ascii=False, indent=2))
            return 0
        expected = build_registry()
        try:
            validate_decision_registry_instance(expected)
        except EvidenceSchemaError as error:
            fail(str(error))
        if args.require_all_accepted:
            require_all_accepted(expected)
        content = generated_bytes(expected)
        if args.write:
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT.write_bytes(content)
            print(f"WROTE {OUTPUT.relative_to(ROOT)}")
            return 0
        try:
            current_content = read_bounded_regular_file(
                OUTPUT,
                limits=REGISTRY_FILE_LIMITS,
                label=OUTPUT.relative_to(ROOT).as_posix(),
            )
        except BoundedJsonError as error:
            fail(str(error))
        current = load_json_bytes(
            current_content,
            OUTPUT.relative_to(ROOT).as_posix(),
        )
        validate_generated(current, expected)
        if current_content != content:
            fail("generated registry formatting is stale")
        validate_output_schema_limits(load_json(SCHEMA))
        accepted = sum(
            decision["status"] == "ACCEPTED" for decision in expected["decisions"]
        )
        print(
            "OK non-normative decision registry: "
            f"{accepted} ACCEPTED, "
            f"{len(expected['decisions']) - accepted} PROPOSED, promotion blocked; "
            "review authorship, role authority, and independence remain external"
        )
        return 0
    except RegistryError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
