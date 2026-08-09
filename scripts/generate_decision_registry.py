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
import ctypes
import errno
import hashlib
import ipaddress
import json
import os
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
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
    maximum_bytes=MAX_ADR_MARKDOWN_BYTES,
    maximum_depth=32,
    maximum_items=100_000,
    maximum_object_members=256,
    maximum_array_items=4096,
    maximum_key_utf8_bytes=128,
    maximum_string_utf8_bytes=4096,
    maximum_total_string_utf8_bytes=MAX_ADR_MARKDOWN_BYTES,
    maximum_integer_chars=128,
    maximum_float_chars=128,
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
WIRE_CASE_ID = re.compile(r"^adr(?:00[1-9]|01[01])\.[a-z0-9-]+\.v1$")
IDENTITY_URI = re.compile(r"^[a-z][a-z0-9+.-]*:[\x21-\x7e]+$")
DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")
RELATIVE_PATH = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$)).+$")
UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
JSON_FENCE = re.compile(r"```json\n(.*?)\n```", re.DOTALL)

SEMANTIC_CORPUS_SCHEMA = "ncp.b01-adr-example-semantics-corpus.v1"
SEMANTIC_PARSER_RESULT_SCHEMA = "ncp.b01-semantic-parser-result.v1"
SEMANTIC_PARSER_RESULT_MEMBERS = (
    "schema",
    "engine",
    "decision_set_sha256",
    "corpus_sha256",
    "case_results",
    "b03_results",
    "status",
    "claim_boundary",
)
SEMANTIC_CLOSURE_EVALUATION_SCHEMA = "ncp.b01-semantic-closure-evaluation.v1"
SEMANTIC_CORPUS_PATH = (
    "prototypes/b01-architecture-evidence/adr-example-semantics/corpus.v1.json"
)
RUST_PARSER_RESULT_PATH = (
    "evidence/implementation/reviews/B01/semantic-closure/rust-parser-result.v1.json"
)
TYPESCRIPT_PARSER_RESULT_PATH = (
    "evidence/implementation/reviews/B01/semantic-closure/"
    "typescript-parser-result.v1.json"
)
SEMANTIC_CAPTURE_DIRECTORY = "evidence/implementation/reviews/B01/semantic-closure"
SEMANTIC_CAPTURE_COMMAND = (
    "python3 scripts/generate_decision_registry.py --capture-semantic-parser-results"
)
SEMANTIC_CAPTURE_WORKFLOW_STATE = "IMPLEMENTED"
SEMANTIC_ENGINE_PROFILE_STATES = {
    "RUST": "NOT_IMPLEMENTED",
    "TYPESCRIPT": "NOT_IMPLEMENTED",
}
SEMANTIC_CAPTURE_RESULT_PATHS = {
    "RUST": RUST_PARSER_RESULT_PATH,
    "TYPESCRIPT": TYPESCRIPT_PARSER_RESULT_PATH,
}
SEMANTIC_PARSER_TIMEOUT_SECONDS = 120
MAX_SEMANTIC_PARSER_STDERR_BYTES = 65_536
MAX_SEMANTIC_TOOL_BYTES = 67_108_864
SEMANTIC_FIXED_ENVIRONMENT = {
    "CARGO_NET_OFFLINE": "true",
    "CARGO_TERM_COLOR": "never",
    "LANG": "C",
    "LC_ALL": "C",
    "NO_COLOR": "1",
    "TZ": "UTC",
}
SEMANTIC_ENGINE_ROOT = "prototypes/b01-architecture-evidence/adr-example-semantics"
RUST_ENGINE_SOURCE_PATHS = (
    f"{SEMANTIC_ENGINE_ROOT}/rust/Cargo.lock",
    f"{SEMANTIC_ENGINE_ROOT}/rust/Cargo.toml",
    f"{SEMANTIC_ENGINE_ROOT}/rust/src/decision.rs",
    f"{SEMANTIC_ENGINE_ROOT}/rust/src/error.rs",
    f"{SEMANTIC_ENGINE_ROOT}/rust/src/main.rs",
    f"{SEMANTIC_ENGINE_ROOT}/rust/src/model.rs",
    f"{SEMANTIC_ENGINE_ROOT}/rust/src/patch.rs",
    f"{SEMANTIC_ENGINE_ROOT}/rust/src/profiles.rs",
    f"{SEMANTIC_ENGINE_ROOT}/rust/src/sha256.rs",
    f"{SEMANTIC_ENGINE_ROOT}/rust/src/source.rs",
    f"{SEMANTIC_ENGINE_ROOT}/rust/src/strict_json.rs",
)
TYPESCRIPT_ENGINE_SOURCE_PATHS = (
    f"{SEMANTIC_ENGINE_ROOT}/typescript/package.json",
    f"{SEMANTIC_ENGINE_ROOT}/typescript/src/canonical-json.ts",
    f"{SEMANTIC_ENGINE_ROOT}/typescript/src/corpus.ts",
    f"{SEMANTIC_ENGINE_ROOT}/typescript/src/decision-binding.ts",
    f"{SEMANTIC_ENGINE_ROOT}/typescript/src/file-io.ts",
    f"{SEMANTIC_ENGINE_ROOT}/typescript/src/json-pointer.ts",
    f"{SEMANTIC_ENGINE_ROOT}/typescript/src/main.ts",
    f"{SEMANTIC_ENGINE_ROOT}/typescript/src/runtime.d.ts",
    f"{SEMANTIC_ENGINE_ROOT}/typescript/src/self-test.ts",
    f"{SEMANTIC_ENGINE_ROOT}/typescript/src/semantics.ts",
    f"{SEMANTIC_ENGINE_ROOT}/typescript/src/strict-json.ts",
    f"{SEMANTIC_ENGINE_ROOT}/typescript/tsconfig.json",
)
SEMANTIC_ADR_SOURCE_PATHS = (
    "docs/adr/0001-separate-simulation-and-plant-sessions.md",
    "docs/adr/0002-contract-identity-and-release-authorization.md",
    "docs/adr/0003-authenticated-production-ingress.md",
    "docs/adr/0004-observer-attach-grants-and-revocation.md",
    "docs/adr/0005-declared-stream-lifecycle.md",
    "docs/adr/0006-body-issued-authority-and-time.md",
    "docs/adr/0007-command-disposition-journal.md",
    "docs/adr/0008-extension-namespace-and-galadriel-separation.md",
    "docs/adr/0009-security-state-rotation-and-revocation.md",
    "docs/adr/0010-plane-qos-retention-and-overload.md",
    "docs/adr/0011-ecosystem-topology-and-handover.md",
    "docs/adr/modules/adr-004-cross-store-observer-closure-and-enrollment.md",
    "docs/adr/modules/adr-009-cross-store-producer-and-compromise-evidence.md",
)
SEMANTIC_REPLAY_SUBJECT_PATHS = (
    SOURCE_RELATIVE,
    SCHEMA_RELATIVE,
    CLOSURE_SOURCE_RELATIVE,
    CLOSURE_SCHEMA_RELATIVE,
    REVIEW_PACKET.relative_to(ROOT).as_posix(),
    GENERATOR,
    SEMANTIC_CORPUS_PATH,
    *SEMANTIC_ADR_SOURCE_PATHS,
)
SEMANTIC_REPLAY_DERIVED_INPUT_PATHS = (OUTPUT.relative_to(ROOT).as_posix(),)
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
EXPECTED_B03_PARAMETER_CONTRACT = {
    "schema": "ncp.b01-b03-parameter-contract.v1",
    "value_kinds": ["BOUNDED_INTEGER", "EXACT_IDENTITY_SET"],
    "envelope_fields": ["minimum", "maximum"],
    "literal_integer_encoding": "POSITIVE_JSON_SAFE_INTEGER",
    "validated_envelope": (
        "POSITIVE_LITERAL_MINIMUM_AND_FINITE_LITERAL_MAXIMUM_WITH_MINIMUM_LTE_MAXIMUM"
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
            "POSITIVE_JSON_SAFE_INTEGER_WITHIN_INCLUSIVE_ACCEPTED_ENVELOPE"
        ),
        "B03_EXACT_IDENTITY_SET_SELECTION_V1": (
            "CANONICAL_UNIQUE_SUBSET_OF_BOUND_ELIGIBILITY_UNIVERSE_WITH_GLOBAL_"
            "NO_EDGE_DENY"
        ),
    },
    "identity_set_measure": "CARDINALITY_OF_CANONICAL_UNIQUE_IDENTITIES",
    "identity_canonicalization": (
        "PRINTABLE_ASCII_U0021_TO_U007E_RAW_BYTE_ASCENDING_UNIQUE"
    ),
    "identity_eligibility_binding": (
        "NONEMPTY_EXACT_B01_UNIVERSE_AND_CONTEXT_DIGEST_WHEN_VALIDATED"
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
        "CANONICAL_SUBSET_OF_BOUND_ELIGIBILITY_UNIVERSE_WITH_CARDINALITY_WITHIN_"
        "ACCEPTED_ENVELOPE"
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
EXPECTED_PARSER_REPLAY_CONTRACT = {
    "schema": "ncp.b01-semantic-parser-replay-contract.v1",
    "mode": "RETAINED_RESULT_PLUS_BOUNDED_DIRECT_REPLAY",
    "result_schema": SEMANTIC_PARSER_RESULT_SCHEMA,
    "self_tests_required": True,
    "timeout_seconds": SEMANTIC_PARSER_TIMEOUT_SECONDS,
    "maximum_stdout_bytes": MAX_JSON_BYTES,
    "maximum_stderr_bytes": MAX_SEMANTIC_PARSER_STDERR_BYTES,
    "process_group_cleanup": "TERM_THEN_KILL_PROCESS_GROUP",
    "rust_command_profile": "RUST_CARGO_OFFLINE_LOCKED_CLOSURE_SELF_TEST_V1",
    "typescript_command_profile": "TYPESCRIPT_BUN_NO_INSTALL_CLOSURE_SELF_TEST_V1",
    "engine_output_requirement": (
        "DIRECT_NCP_B01_SEMANTIC_PARSER_RESULT_V1_NO_ADAPTER"
    ),
    "dependency_resolution_mode": (
        "RUST_CARGO_OFFLINE_LOCKED_TYPESCRIPT_BUN_NO_INSTALL"
    ),
    "process_network_isolation": "NOT_PROVIDED_LOCAL_REPLAY_ONLY",
    "dependency_cache_requirement": (
        "RUST_AMBIENT_CARGO_HOME_PRESEEDED_BY_GATE_TYPESCRIPT_NONE"
    ),
    "repository_execution_root": "TEMPORARY_BOUND_INPUT_SNAPSHOT",
    "snapshot_postcondition": "EXACT_FILE_SET_AND_BYTES_UNCHANGED",
    "derived_registry_receipt_binding": (
        "DECISION_SET_SHA256_ONLY_OUTPUT_BYTES_EXCLUDED_TO_PREVENT_SELF_REFERENCE"
    ),
    "tool_identity": "OBSERVED_VERSION_AND_EXECUTABLE_DIGEST_NOT_PROVENANCE",
    "source_tree_build_output": "ABSENT_BEFORE_AND_AFTER",
    "capture_command": SEMANTIC_CAPTURE_COMMAND,
    "capture_target_directory": SEMANTIC_CAPTURE_DIRECTORY,
    "capture_result_paths": list(SEMANTIC_CAPTURE_RESULT_PATHS.values()),
    "capture_preconditions": (
        "CURRENT_EXACT_OPEN_REGISTRY_ONLY_DUAL_NOT_RUN_PARSER_CLOSURE_"
        "BLOCKERS_COMPLETE_CURRENT_CORPUS_VALIDATED_B03_DEFERRAL_ENVELOPES"
    ),
    "capture_write_policy": ("BOTH_VALID_PASS_THEN_WRITE_ONCE_DIRECTORY_ATOMIC_RENAME"),
    "capture_workflow_state": "IMPLEMENTED",
    "engine_profile_states": copy.deepcopy(SEMANTIC_ENGINE_PROFILE_STATES),
    "capture_failure_effect": "WRITE_NEITHER_RESULT",
}
EXPECTED_B03_BINDINGS = {
    "ADR-002-Q01": (
        "protocol-reviewer",
        (("STABLE_CORE_FILE_IDENTITIES", "EXACT_IDENTITY_SET"),),
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
        ),
    ),
    "ADR-010-Q02": (
        "real-time-performance-reviewer",
        (
            ("CONTROL_RPC_QUEUE_CAPACITY", "BOUNDED_INTEGER"),
            ("CONTROL_RPC_DEADLINE_NS", "BOUNDED_INTEGER"),
            ("ACTION_COMMAND_QUEUE_CAPACITY", "BOUNDED_INTEGER"),
            ("ACTION_COMMAND_DEADLINE_NS", "BOUNDED_INTEGER"),
            ("OBSERVATION_DISPOSITION_QUEUE_CAPACITY", "BOUNDED_INTEGER"),
            ("OBSERVATION_DISPOSITION_DEADLINE_NS", "BOUNDED_INTEGER"),
            ("EXTENSION_QUEUE_CAPACITY", "BOUNDED_INTEGER"),
            ("EXTENSION_DEADLINE_NS", "BOUNDED_INTEGER"),
        ),
    ),
    "ADR-011-Q01": (
        "release-package-tooling-reviewer",
        (
            ("EXTENSION_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("PACKAGE_FEATURE_IDENTITIES", "EXACT_IDENTITY_SET"),
            ("CONSUMER_INVENTORY_IDENTITIES", "EXACT_IDENTITY_SET"),
        ),
    ),
}
EXPECTED_WIRE_CASE_CONTRACT = {
    "complete_positive": {
        "scope": "COMPLETE_PROPOSED_WIRE_OBJECT",
        "polarity": "POSITIVE",
        "expected_profile_result": "MATCH_COMPLETE_NON_AUTHORIZING",
        "production_admission": "NOT_EVALUATED",
    },
    "complete_hostile": {
        "scope": "COMPLETE_PROPOSED_WIRE_OBJECT",
        "polarity": "NEGATIVE",
        "mutation_relation": "EXACTLY_ONE_SEMANTIC_DELTA_FROM_BOUND_POSITIVE",
        "expected_profile_result": "REJECT",
        "production_admission": "REJECT",
    },
}
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
SemanticParserRunner = Callable[[str], tuple[bytes, dict[str, Any]]]


class RegistryError(ValueError):
    """The non-normative decision registry is malformed or overclaims status."""


def fail(message: str) -> NoReturn:
    raise RegistryError(message)


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


def exact_keys(value: dict[str, Any], expected: set[str], path: str) -> None:
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

    The source declares stable requirements and paths only. Observed corpus and
    parser-result bytes are evaluated after the decision set exists so no evidence
    artifact can become a digest ancestor of itself. Future B03 selections remain
    outside the B01 decision-set identity.
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
            "wire_case_contract",
            "b03_parameter_contract",
            "parser_replay_contract",
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
    if closure_source["wire_case_contract"] != EXPECTED_WIRE_CASE_CONTRACT:
        fail("closure.wire_case_contract differs from the fail-closed contract")
    if closure_source["b03_parameter_contract"] != EXPECTED_B03_PARAMETER_CONTRACT:
        fail("closure.b03_parameter_contract differs from the fail-closed contract")
    if closure_source["parser_replay_contract"] != EXPECTED_PARSER_REPLAY_CONTRACT:
        fail("closure.parser_replay_contract differs from the direct replay contract")

    required_role_ids = {
        requirement["role_id"]
        for decision in generated
        for requirement in decision["required_reviews"]
    }
    components = closure_source["excluded_no_edge_components"]
    component_ids: list[str] = []
    prohibited_roles: set[str] = set()
    observed_components: dict[str, dict[str, set[str]]] = {}
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
        roles = set(component["prohibited_review_role_ids"])
        edge_classes = set(component["prohibited_edge_classes"])
        canonical_aliases = component["canonical_aliases"]
        if len(roles) != len(component["prohibited_review_role_ids"]):
            fail(f"{path}.prohibited_review_role_ids contains duplicates")
        if len(edge_classes) != len(component["prohibited_edge_classes"]):
            fail(f"{path}.prohibited_edge_classes contains duplicates")
        if tuple(component["prohibited_edge_classes"]) != EXPECTED_NO_EDGE_CLASSES:
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
        for role_id in roles:
            if not isinstance(role_id, str) or not ROLE_ID.fullmatch(role_id):
                fail(f"{path}.prohibited_review_role_ids contains an invalid role")
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
    wire_case_ids: list[str] = []
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
            {"id", "adr_source_set_sha256", "questions", "wire_requirements"},
            path,
        )
        identifier = closure["id"]
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
            validation_state = deferral["validation_state"]
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
                else:
                    if not eligible_identities or observed_digest != (
                        b03_eligibility_set_sha256(
                            question_id,
                            parameter_id,
                            eligible_identities,
                        )
                    ):
                        fail(
                            f"{universe_path} does not bind a nonempty exact "
                            "eligibility universe and context digest"
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
                bounded_integer(
                    minimum,
                    f"{parameter_path}.minimum",
                    minimum=1,
                    maximum=MAX_B03_LITERAL_INTEGER,
                )
                bounded_integer(
                    maximum,
                    f"{parameter_path}.maximum",
                    minimum=1,
                    maximum=MAX_B03_LITERAL_INTEGER,
                )
                if minimum > maximum:
                    fail(f"{parameter_path} has inverted bounds")
                if parameter["value_kind"] == "EXACT_IDENTITY_SET" and maximum > len(
                    eligibility_by_parameter[parameter_id]
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

        wire = closure["wire_requirements"]
        exact_keys(
            wire,
            {
                "corpus_path",
                "required_corpus_status",
                "required_source_paths",
                "complete_positive",
                "complete_hostile",
                "rust_parser_evidence",
                "typescript_parser_evidence",
            },
            f"{path}.wire_requirements",
        )
        if (
            wire["corpus_path"] != SEMANTIC_CORPUS_PATH
            or wire["required_corpus_status"] != "COMPLETE_CURRENT"
        ):
            fail(f"{path}.wire_requirements does not require the complete corpus")
        expected_source_paths = [
            source_identity["path"]
            for source_identity in generated_by_id[identifier]["source_set"]["sources"]
        ]
        if wire["required_source_paths"] != expected_source_paths:
            fail(f"{path}.wire_requirements omits or reorders an ADR source")
        positive_requirements = wire["complete_positive"]
        hostile_requirements = wire["complete_hostile"]
        if (
            not isinstance(positive_requirements, list)
            or not isinstance(hostile_requirements, list)
            or len(positive_requirements) != len(expected_source_paths)
            or len(hostile_requirements) != len(expected_source_paths)
        ):
            fail(
                f"{path}.wire_requirements must require one positive and one "
                "hostile complete case for every ADR source"
            )
        positive_by_source: dict[str, str] = {}
        for case_index, requirement in enumerate(positive_requirements):
            case_path = f"{path}.wire_requirements.complete_positive[{case_index}]"
            exact_keys(
                requirement,
                {"case_id", "source_path", "required_scope", "required_polarity"},
                case_path,
            )
            case_id = requirement["case_id"]
            if (
                not isinstance(case_id, str)
                or not WIRE_CASE_ID.fullmatch(case_id)
                or not case_id.startswith(identifier.lower().replace("-", "") + ".")
            ):
                fail(f"{case_path}.case_id is invalid")
            wire_case_ids.append(case_id)
            if (
                requirement["required_scope"] != "COMPLETE_PROPOSED_WIRE_OBJECT"
                or requirement["required_polarity"] != "POSITIVE"
                or requirement["source_path"] not in expected_source_paths
            ):
                fail(f"{case_path} weakens source-bound completeness")
            if requirement["source_path"] in positive_by_source:
                fail(f"{case_path} duplicates a positive source requirement")
            positive_by_source[requirement["source_path"]] = case_id
        hostile_sources: set[str] = set()
        for case_index, requirement in enumerate(hostile_requirements):
            case_path = f"{path}.wire_requirements.complete_hostile[{case_index}]"
            exact_keys(
                requirement,
                {
                    "case_id",
                    "source_path",
                    "positive_case_id",
                    "mutation_relation",
                    "required_scope",
                    "required_polarity",
                },
                case_path,
            )
            case_id = requirement["case_id"]
            source_path = requirement["source_path"]
            if (
                not isinstance(case_id, str)
                or not WIRE_CASE_ID.fullmatch(case_id)
                or not case_id.startswith(identifier.lower().replace("-", "") + ".")
            ):
                fail(f"{case_path}.case_id is invalid")
            wire_case_ids.append(case_id)
            if (
                source_path not in expected_source_paths
                or source_path in hostile_sources
                or requirement["positive_case_id"]
                != positive_by_source.get(source_path)
                or requirement["mutation_relation"]
                != "EXACTLY_ONE_SEMANTIC_DELTA_FROM_BOUND_POSITIVE"
                or requirement["required_scope"] != "COMPLETE_PROPOSED_WIRE_OBJECT"
                or requirement["required_polarity"] != "NEGATIVE"
            ):
                fail(f"{case_path} is not a one-delta source-bound hostile case")
            hostile_sources.add(source_path)
        if list(positive_by_source) != expected_source_paths or hostile_sources != set(
            expected_source_paths
        ):
            fail(f"{path}.wire_requirements does not cover every ADR source")
        for field, engine, result_path in (
            ("rust_parser_evidence", "RUST", RUST_PARSER_RESULT_PATH),
            (
                "typescript_parser_evidence",
                "TYPESCRIPT",
                TYPESCRIPT_PARSER_RESULT_PATH,
            ),
        ):
            requirement = wire[field]
            exact_keys(
                requirement,
                {"engine", "result_path", "required_status"},
                f"{path}.wire_requirements.{field}",
            )
            if requirement != {
                "engine": engine,
                "result_path": result_path,
                "required_status": "PASS",
            }:
                fail(f"{path}.wire_requirements.{field} is not exact")

    if tuple(closure_ids) != EXPECTED_IDS:
        fail("closure.decisions IDs are missing or out of order")
    if len(question_ids) != len(set(question_ids)):
        fail("closure.decisions contains duplicate question IDs")
    if len(document_anchors) != len(set(document_anchors)):
        fail("closure.decisions reuses a question or resolution anchor")
    if len(b03_source_anchors) != len(set(b03_source_anchors)):
        fail("closure.decisions reuses a B03 source anchor")
    if len(wire_case_ids) != len(set(wire_case_ids)):
        fail("closure.decisions contains duplicate required wire-case IDs")

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


def semantic_engine_source_identities(engine: str) -> list[dict[str, Any]]:
    paths = (
        RUST_ENGINE_SOURCE_PATHS
        if engine == "RUST"
        else TYPESCRIPT_ENGINE_SOURCE_PATHS
        if engine == "TYPESCRIPT"
        else None
    )
    if paths is None:
        fail(f"unknown semantic parser engine {engine}")
    identities = [
        repository_file_identity(
            ROOT / path,
            maximum_bytes=262_144,
        )
        for path in paths
    ]
    if [identity["path"] for identity in identities] != sorted(set(paths)):
        fail(f"{engine} semantic parser source inventory is not canonical")
    if sum(identity["bytes"] for identity in identities) > 2_097_152:
        fail(f"{engine} semantic parser source inventory is too large")
    return identities


def semantic_replay_input_snapshot(
    engine: str,
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    """Read the exact bounded file set copied into a replay-only repository."""

    engine_paths = (
        RUST_ENGINE_SOURCE_PATHS
        if engine == "RUST"
        else TYPESCRIPT_ENGINE_SOURCE_PATHS
        if engine == "TYPESCRIPT"
        else None
    )
    if engine_paths is None:
        fail(f"unknown semantic parser engine {engine}")
    paths = sorted(
        set(
            (
                *SEMANTIC_REPLAY_SUBJECT_PATHS,
                *SEMANTIC_REPLAY_DERIVED_INPUT_PATHS,
                *engine_paths,
            )
        )
    )
    if len(paths) != (
        len(SEMANTIC_REPLAY_SUBJECT_PATHS)
        + len(SEMANTIC_REPLAY_DERIVED_INPUT_PATHS)
        + len(engine_paths)
    ):
        fail(f"{engine} semantic replay input inventory contains duplicates")
    contents: dict[str, bytes] = {}
    identities: list[dict[str, Any]] = []
    total_bytes = 0
    for relative in paths:
        relative_path(relative, f"{engine} semantic replay input path")
        maximum_bytes = (
            MAX_ADR_MARKDOWN_BYTES if relative.endswith(".md") else MAX_JSON_BYTES
        )
        content = read_repository_regular_file(
            relative,
            maximum_bytes=maximum_bytes,
            label=f"{engine} semantic replay input {relative}",
        )
        total_bytes += len(content)
        if total_bytes > MAX_TOTAL_EVIDENCE_BYTES:
            fail(f"{engine} semantic replay input set exceeds its aggregate bound")
        contents[relative] = content
        identities.append(
            {
                "path": relative,
                "sha256": sha256_bytes(content),
                "bytes": len(content),
            }
        )
    return identities, contents


def semantic_replay_registry_binding(registry_content: bytes) -> dict[str, str]:
    registry_path = OUTPUT.relative_to(ROOT).as_posix()
    registry = load_json_bytes(registry_content, f"semantic replay {registry_path}")
    decision_identity = registry.get("decision_set")
    if not isinstance(decision_identity, dict):
        fail("semantic replay registry lacks a decision-set identity")
    if (
        decision_identity.get("schema") != DECISION_SET_SCHEMA
        or decision_identity.get("digest_algorithm")
        != "sha256(domain || u64be(projection_bytes) || projection)"
        or decision_identity.get("domain_hex") != DECISION_SET_DOMAIN.hex()
    ):
        fail("semantic replay registry decision-set identity is invalid")
    decision_set_sha256 = validate_hex(
        decision_identity.get("sha256"),
        HEX64,
        "semantic replay registry decision_set.sha256",
    )
    return {
        "path": registry_path,
        "decision_set_sha256": decision_set_sha256,
    }


def materialize_semantic_replay_snapshot(
    snapshot_root: Path,
    contents: dict[str, bytes],
) -> None:
    for relative, content in contents.items():
        destination = snapshot_root.joinpath(*PurePosixPath(relative).parts)
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(destination, flags, 0o400)
        except OSError as error:
            fail(f"cannot create isolated semantic replay input {relative}: {error}")
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            fail(f"cannot write isolated semantic replay input {relative}: {error}")
        finally:
            os.close(descriptor)


def validate_semantic_replay_snapshot(
    snapshot_root: Path,
    expected_identities: list[dict[str, Any]],
) -> None:
    expected_paths = {identity["path"] for identity in expected_identities}
    expected_directories = {"."}
    for relative in expected_paths:
        parent = PurePosixPath(relative).parent
        while parent != PurePosixPath("."):
            expected_directories.add(parent.as_posix())
            parent = parent.parent
    observed_paths: set[str] = set()
    observed_directories: set[str] = set()
    for directory, directories, files in os.walk(snapshot_root, followlinks=False):
        directory_path = Path(directory)
        relative_directory = directory_path.relative_to(snapshot_root).as_posix()
        observed_directories.add(relative_directory)
        for name in [*directories, *files]:
            candidate = directory_path / name
            try:
                metadata = candidate.lstat()
            except OSError as error:
                fail(f"cannot inspect isolated semantic replay path: {error}")
            if stat.S_ISLNK(metadata.st_mode):
                fail("isolated semantic replay created a symbolic link")
        for name in files:
            relative = (directory_path / name).relative_to(snapshot_root).as_posix()
            observed_paths.add(relative)
    if observed_paths != expected_paths or observed_directories != expected_directories:
        fail("isolated semantic replay changed its exact file or directory set")
    observed_identities: list[dict[str, Any]] = []
    for expected in expected_identities:
        content = read_physical_regular_file(
            snapshot_root,
            expected["path"],
            maximum_bytes=(
                MAX_ADR_MARKDOWN_BYTES
                if expected["path"].endswith(".md")
                else MAX_JSON_BYTES
            ),
            label=f"isolated semantic replay input {expected['path']}",
        )
        observed_identities.append(
            {
                "path": expected["path"],
                "sha256": sha256_bytes(content),
                "bytes": len(content),
            }
        )
    if observed_identities != expected_identities:
        fail("isolated semantic replay changed an input byte identity")


def require_semantic_source_tree_outputs_absent() -> None:
    outputs = (
        ROOT / SEMANTIC_ENGINE_ROOT / "rust" / "target",
        ROOT / SEMANTIC_ENGINE_ROOT / "typescript" / "dist",
        ROOT / SEMANTIC_ENGINE_ROOT / "typescript" / "node_modules",
    )
    present: list[str] = []
    for output in outputs:
        try:
            output.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            fail(f"cannot inspect semantic parser build-output path: {error}")
        present.append(output.relative_to(ROOT).as_posix())
    if present:
        fail(f"semantic parser source tree contains build/cache output: {present}")


def semantic_process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def terminate_semantic_process(process: subprocess.Popen[bytes]) -> None:
    process_group_id = process.pid
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + 0.25
    while (
        semantic_process_group_exists(process_group_id) and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    if semantic_process_group_exists(process_group_id):
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass


def bounded_semantic_process(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    stdout_limit: int,
    timeout_seconds: int,
    label: str,
) -> bytes:
    try:
        process = subprocess.Popen(  # noqa: S603
            command,
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as error:
        fail(f"cannot start {label}: {error}")
    if process.stdout is None or process.stderr is None:
        terminate_semantic_process(process)
        fail(f"{label} did not expose bounded output pipes")
    stream_selector = selectors.DefaultSelector()
    streams = {
        process.stdout: ("stdout", stdout_limit),
        process.stderr: ("stderr", MAX_SEMANTIC_PARSER_STDERR_BYTES),
    }
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    for stream in streams:
        os.set_blocking(stream.fileno(), False)
        stream_selector.register(stream, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout_seconds
    try:
        while stream_selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                terminate_semantic_process(process)
                fail(f"{label} exceeded its {timeout_seconds}-second timeout")
            for key, _mask in stream_selector.select(min(remaining, 0.25)):
                stream = key.fileobj
                name, limit = streams[stream]
                try:
                    chunk = os.read(stream.fileno(), 8192)
                except BlockingIOError:
                    continue
                if not chunk:
                    stream_selector.unregister(stream)
                    continue
                if len(buffers[name]) + len(chunk) > limit:
                    terminate_semantic_process(process)
                    fail(f"{label} {name} exceeds its {limit}-byte bound")
                buffers[name].extend(chunk)
        try:
            return_code = process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            terminate_semantic_process(process)
            fail(f"{label} did not terminate within its timeout")
        terminate_semantic_process(process)
    finally:
        stream_selector.close()
        process.stdout.close()
        process.stderr.close()
    stderr = bytes(buffers["stderr"])
    stdout = bytes(buffers["stdout"])
    if return_code != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()[-2000:]
        fail(f"{label} exited {return_code}: {detail or 'no diagnostic'}")
    if stderr:
        fail(f"{label} emitted stderr on a successful run")
    if not stdout:
        fail(f"{label} emitted no output")
    return stdout


def semantic_parser_command_contract(
    engine: str,
) -> tuple[tuple[str, ...], str, list[str]]:
    if engine == "RUST":
        tool_names = ("cargo", "rustc")
        command_profile = "RUST_CARGO_OFFLINE_LOCKED_CLOSURE_SELF_TEST_V1"
        argv = [
            "cargo",
            "run",
            "--quiet",
            "--offline",
            "--locked",
            "--manifest-path",
            f"{SEMANTIC_ENGINE_ROOT}/rust/Cargo.toml",
            "--",
            "--corpus",
            SEMANTIC_CORPUS_PATH,
            "--repo-root",
            ".",
            "--closure-source",
            CLOSURE_SOURCE_RELATIVE,
            "--result-schema",
            SEMANTIC_PARSER_RESULT_SCHEMA,
            "--self-test",
        ]
    elif engine == "TYPESCRIPT":
        tool_names = ("bun",)
        command_profile = "TYPESCRIPT_BUN_NO_INSTALL_CLOSURE_SELF_TEST_V1"
        argv = [
            "bun",
            "run",
            "--no-install",
            "--no-env-file",
            "--no-orphans",
            f"{SEMANTIC_ENGINE_ROOT}/typescript/src/main.ts",
            "--corpus",
            SEMANTIC_CORPUS_PATH,
            "--repo-root",
            ".",
            "--closure-source",
            CLOSURE_SOURCE_RELATIVE,
            "--result-schema",
            SEMANTIC_PARSER_RESULT_SCHEMA,
            "--self-test",
        ]
    else:
        fail(f"unknown semantic parser engine {engine}")
    return tool_names, command_profile, argv


def run_semantic_parser(engine: str) -> tuple[bytes, dict[str, Any]]:
    tool_names, command_profile, argv = semantic_parser_command_contract(engine)
    tool_paths: dict[str, Path] = {}
    for name in tool_names:
        executable = shutil.which(name)
        if executable is None:
            fail(f"{name} is unavailable for {engine} semantic parser replay")
        try:
            tool_paths[name] = Path(executable).resolve(strict=True)
        except OSError as error:
            fail(f"cannot resolve {name} for {engine} semantic parser replay: {error}")
    inherited_environment = {"PATH": os.environ.get("PATH", "")}
    if not inherited_environment["PATH"]:
        fail(f"{engine} semantic parser replay requires a nonempty PATH")
    if engine == "RUST":
        inherited_environment["CARGO_HOME"] = os.environ.get(
            "CARGO_HOME", str(Path.home() / ".cargo")
        )
        inherited_environment["RUSTUP_HOME"] = os.environ.get(
            "RUSTUP_HOME", str(Path.home() / ".rustup")
        )
    inherited_keys = tuple(sorted(inherited_environment))
    environment = copy.deepcopy(inherited_environment)
    fixed_environment = copy.deepcopy(SEMANTIC_FIXED_ENVIRONMENT)
    environment.update(fixed_environment)
    environment_commitment = sha256_bytes(
        json.dumps(
            inherited_environment,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )

    def tool_identities(cwd: Path) -> list[dict[str, Any]]:
        observed: list[dict[str, str]] = []
        for name in tool_names:
            output = bounded_semantic_process(
                [str(tool_paths[name]), "--version"],
                cwd=cwd,
                environment=environment,
                stdout_limit=4096,
                timeout_seconds=10,
                label=f"{name} version probe",
            )
            version = output.decode("utf-8", errors="strict").strip()
            version_pattern = (
                r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]{1,64})?"
                if name == "bun"
                else rf"{name} [0-9]+\.[0-9]+\.[0-9]+(?:[-+ ][ -~]{{1,96}})?"
            )
            if not re.fullmatch(version_pattern, version):
                fail(f"{name} emitted an unrecognized version identity")
            try:
                executable_content = read_bounded_regular_file(
                    tool_paths[name],
                    limits=FileSnapshotLimits(
                        minimum_bytes=1,
                        maximum_bytes=MAX_SEMANTIC_TOOL_BYTES,
                    ),
                    label=f"{name} resolved executable",
                )
            except BoundedJsonError as error:
                fail(str(error))
            observed.append(
                {
                    "name": name,
                    "version": version,
                    "executable_sha256": sha256_bytes(executable_content),
                    "executable_bytes": len(executable_content),
                }
            )
        return observed

    require_semantic_source_tree_outputs_absent()
    snapshot_identities, snapshot_contents = semantic_replay_input_snapshot(engine)
    public_snapshot_identities = [
        identity
        for identity in snapshot_identities
        if identity["path"] not in SEMANTIC_REPLAY_DERIVED_INPUT_PATHS
    ]
    registry_binding = semantic_replay_registry_binding(
        snapshot_contents[OUTPUT.relative_to(ROOT).as_posix()]
    )
    source_identities = [
        identity
        for identity in snapshot_identities
        if identity["path"]
        in (
            RUST_ENGINE_SOURCE_PATHS
            if engine == "RUST"
            else TYPESCRIPT_ENGINE_SOURCE_PATHS
        )
    ]
    with tempfile.TemporaryDirectory(prefix="ncp-b01-semantic-replay-") as temporary:
        temporary_root = Path(temporary)
        snapshot_root = temporary_root / "repository"
        isolated_home = temporary_root / "home"
        isolated_tmp = temporary_root / "tmp"
        isolated_cache = temporary_root / "build-cache"
        for directory in (
            snapshot_root,
            isolated_home,
            isolated_tmp,
            isolated_cache,
        ):
            directory.mkdir(mode=0o700)
        materialize_semantic_replay_snapshot(snapshot_root, snapshot_contents)
        validate_semantic_replay_snapshot(snapshot_root, snapshot_identities)
        environment["HOME"] = str(isolated_home)
        environment["TMPDIR"] = str(isolated_tmp)
        if engine == "RUST":
            environment["CARGO_TARGET_DIR"] = str(isolated_cache)
        else:
            environment["BUN_INSTALL_CACHE_DIR"] = str(isolated_cache)
        before_tools = tool_identities(snapshot_root)
        try:
            stdout = bounded_semantic_process(
                [str(tool_paths[argv[0]]), *argv[1:]],
                cwd=snapshot_root,
                environment=environment,
                stdout_limit=MAX_JSON_BYTES,
                timeout_seconds=SEMANTIC_PARSER_TIMEOUT_SECONDS,
                label=f"{engine} semantic parser replay",
            )
        finally:
            validate_semantic_replay_snapshot(snapshot_root, snapshot_identities)
            require_semantic_source_tree_outputs_absent()
        after_tools = tool_identities(snapshot_root)
    if after_tools != before_tools:
        fail(f"{engine} semantic parser tool identity changed during replay")
    current_snapshot_identities, _ = semantic_replay_input_snapshot(engine)
    if current_snapshot_identities != snapshot_identities:
        fail(f"{engine} semantic replay input bytes changed during replay")
    return stdout, {
        "schema": "ncp.b01-semantic-parser-replay.v1",
        "evidence_class": "OBSERVED_LOCAL_REPLAY_NOT_PROVENANCE",
        "command_profile": command_profile,
        "argv": argv,
        "working_directory": "TEMPORARY_BOUND_INPUT_SNAPSHOT_ROOT",
        "fixed_environment": fixed_environment,
        "inherited_environment_keys": list(inherited_keys),
        "inherited_environment_sha256": environment_commitment,
        "isolated_environment_keys": sorted(
            {
                "HOME",
                "TMPDIR",
                "CARGO_TARGET_DIR" if engine == "RUST" else "BUN_INSTALL_CACHE_DIR",
            }
        ),
        "isolated_cache_directory": True,
        "isolated_cache_environment_key": (
            "CARGO_TARGET_DIR" if engine == "RUST" else "BUN_INSTALL_CACHE_DIR"
        ),
        "dependency_resolution_mode": (
            "CARGO_OFFLINE_LOCKED" if engine == "RUST" else "BUN_NO_INSTALL"
        ),
        "process_network_isolation": "NOT_PROVIDED_LOCAL_REPLAY_ONLY",
        "dependency_cache_mode": (
            "AMBIENT_CARGO_HOME_OFFLINE" if engine == "RUST" else "NOT_USED_NO_INSTALL"
        ),
        "timeout_seconds": SEMANTIC_PARSER_TIMEOUT_SECONDS,
        "tools": before_tools,
        "engine_sources": source_identities,
        "repository_snapshot_inputs": public_snapshot_identities,
        "repository_snapshot_postcondition": "EXACT_FILE_SET_AND_BYTES_UNCHANGED",
        "derived_registry_binding": registry_binding,
        "stdout_sha256": sha256_bytes(stdout),
        "stdout_bytes": len(stdout),
        "stderr_bytes": 0,
        "exit_code": 0,
        "source_tree_build_output_absent": True,
    }


def validate_semantic_replay_receipt(receipt: dict[str, Any], engine: str) -> None:
    path = f"semantic parser result {engine}.replay_receipt"
    exact_keys(
        receipt,
        {
            "schema",
            "evidence_class",
            "command_profile",
            "argv",
            "working_directory",
            "fixed_environment",
            "inherited_environment_keys",
            "inherited_environment_sha256",
            "isolated_environment_keys",
            "isolated_cache_directory",
            "isolated_cache_environment_key",
            "dependency_resolution_mode",
            "process_network_isolation",
            "dependency_cache_mode",
            "timeout_seconds",
            "tools",
            "engine_sources",
            "repository_snapshot_inputs",
            "repository_snapshot_postcondition",
            "derived_registry_binding",
            "stdout_sha256",
            "stdout_bytes",
            "stderr_bytes",
            "exit_code",
            "source_tree_build_output_absent",
        },
        path,
    )
    tool_names, command_profile, argv = semantic_parser_command_contract(engine)
    if (
        receipt["schema"] != "ncp.b01-semantic-parser-replay.v1"
        or receipt["evidence_class"] != "OBSERVED_LOCAL_REPLAY_NOT_PROVENANCE"
        or receipt["command_profile"] != command_profile
        or receipt["argv"] != argv
        or receipt["working_directory"] != "TEMPORARY_BOUND_INPUT_SNAPSHOT_ROOT"
        or receipt["fixed_environment"] != SEMANTIC_FIXED_ENVIRONMENT
        or receipt["isolated_environment_keys"]
        != sorted(
            {
                "HOME",
                "TMPDIR",
                "CARGO_TARGET_DIR" if engine == "RUST" else "BUN_INSTALL_CACHE_DIR",
            }
        )
        or receipt["isolated_cache_directory"] is not True
        or receipt["isolated_cache_environment_key"]
        != ("CARGO_TARGET_DIR" if engine == "RUST" else "BUN_INSTALL_CACHE_DIR")
        or receipt["dependency_resolution_mode"]
        != ("CARGO_OFFLINE_LOCKED" if engine == "RUST" else "BUN_NO_INSTALL")
        or receipt["process_network_isolation"] != "NOT_PROVIDED_LOCAL_REPLAY_ONLY"
        or receipt["dependency_cache_mode"]
        != ("AMBIENT_CARGO_HOME_OFFLINE" if engine == "RUST" else "NOT_USED_NO_INSTALL")
        or receipt["timeout_seconds"] != SEMANTIC_PARSER_TIMEOUT_SECONDS
        or receipt["stderr_bytes"] != 0
        or receipt["exit_code"] != 0
        or receipt["repository_snapshot_postcondition"]
        != "EXACT_FILE_SET_AND_BYTES_UNCHANGED"
        or receipt["source_tree_build_output_absent"] is not True
    ):
        fail(f"{path} differs from the bounded direct-replay contract")
    inherited_keys = receipt["inherited_environment_keys"]
    expected_inherited_keys = (
        ["CARGO_HOME", "PATH", "RUSTUP_HOME"] if engine == "RUST" else ["PATH"]
    )
    if (
        not isinstance(inherited_keys, list)
        or inherited_keys != expected_inherited_keys
    ):
        fail(f"{path}.inherited_environment_keys differs from the exact profile")
    validate_hex(
        receipt["inherited_environment_sha256"],
        HEX64,
        f"{path}.inherited_environment_sha256",
    )
    tools = receipt["tools"]
    if (
        not isinstance(tools, list)
        or [tool.get("name") for tool in tools if isinstance(tool, dict)]
        != list(tool_names)
        or len(tools) != len(tool_names)
    ):
        fail(f"{path}.tools differs from the exact engine tool set")
    for index, tool in enumerate(tools):
        exact_keys(
            tool,
            {"name", "version", "executable_sha256", "executable_bytes"},
            f"{path}.tools[{index}]",
        )
        version = bounded_string(
            tool["version"], f"{path}.tools[{index}].version", maximum=128
        )
        version_pattern = (
            r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]{1,64})?"
            if tool["name"] == "bun"
            else rf"{tool['name']} [0-9]+\.[0-9]+\.[0-9]+(?:[-+ ][ -~]{{1,96}})?"
        )
        if not re.fullmatch(version_pattern, version):
            fail(f"{path}.tools[{index}] has an invalid observed version")
        validate_hex(
            tool["executable_sha256"],
            HEX64,
            f"{path}.tools[{index}].executable_sha256",
        )
        bounded_integer(
            tool["executable_bytes"],
            f"{path}.tools[{index}].executable_bytes",
            minimum=1,
            maximum=MAX_SEMANTIC_TOOL_BYTES,
        )
    current_inputs, _ = semantic_replay_input_snapshot(engine)
    current_public_inputs = [
        identity
        for identity in current_inputs
        if identity["path"] not in SEMANTIC_REPLAY_DERIVED_INPUT_PATHS
    ]
    if receipt["repository_snapshot_inputs"] != current_public_inputs:
        fail(f"{path}.repository_snapshot_inputs differs from current exact inputs")
    current_registry = read_repository_regular_file(
        OUTPUT.relative_to(ROOT).as_posix(),
        maximum_bytes=MAX_JSON_BYTES,
        label="semantic replay derived registry",
    )
    if receipt["derived_registry_binding"] != semantic_replay_registry_binding(
        current_registry
    ):
        fail(f"{path}.derived_registry_binding differs from the current decision set")
    engine_paths = (
        RUST_ENGINE_SOURCE_PATHS if engine == "RUST" else TYPESCRIPT_ENGINE_SOURCE_PATHS
    )
    expected_engine_sources = [
        identity for identity in current_inputs if identity["path"] in engine_paths
    ]
    if receipt["engine_sources"] != expected_engine_sources:
        fail(f"{path}.engine_sources differs from current exact source bytes")
    validate_hex(receipt["stdout_sha256"], HEX64, f"{path}.stdout_sha256")
    bounded_integer(
        receipt["stdout_bytes"],
        f"{path}.stdout_bytes",
        minimum=1,
        maximum=MAX_JSON_BYTES,
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


def canonical_wire_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def bound_wire_object(
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
        "path",
        "json_fence_ordinal",
        "adr_byte_length",
        "adr_sha256",
        "fence_byte_length",
        "fence_sha256",
    }:
        return None
    source_identity = requirement["source_identity"]
    ordinal = source_value.get("json_fence_ordinal")
    if (
        source_value.get("adr") != requirement["decision_id"]
        or source_value.get("path") != source_identity["path"]
        or source_value.get("adr_byte_length") != source_identity["bytes"]
        or source_value.get("adr_sha256") != source_identity["sha256"]
        or type(ordinal) is not int
        or not 1 <= ordinal <= 64
    ):
        return None
    content = read_repository_regular_file(
        source_identity["path"],
        maximum_bytes=MAX_ADR_MARKDOWN_BYTES,
        label=f"{case_path} bound proposed-wire source",
    )
    if (
        len(content) != source_identity["bytes"]
        or sha256_bytes(content) != source_identity["sha256"]
    ):
        return None
    try:
        fences = JSON_FENCE.findall(content.decode("utf-8"))
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
            label=f"{case_path} bound proposed-wire JSON fence",
            limits=ADR_FENCE_JSON_LIMITS,
        )
    except RegistryError:
        return None
    return wire_object if isinstance(wire_object, dict) else None


def apply_single_wire_mutation(
    positive: dict[str, Any], mutation: Any
) -> dict[str, Any] | None:
    if not isinstance(mutation, dict):
        return None
    operation = mutation.get("op")
    required_keys = {"target", "op", "path"}
    if operation in {"ADD", "REPLACE"}:
        required_keys.add("value")
    if set(mutation) != required_keys or mutation.get("target") != "DOCUMENT":
        return None
    if operation not in {"ADD", "REMOVE", "REPLACE"}:
        return None
    scalar_types = (type(None), bool, int, str)
    if (
        operation in {"ADD", "REPLACE"}
        and type(mutation.get("value")) not in scalar_types
    ):
        return None
    path = mutation.get("path")
    if (
        not isinstance(path, str)
        or not 1 <= len(path) <= 512
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
        elif isinstance(parent, list) and segment.isascii() and segment.isdigit():
            offset = int(segment)
            if offset >= len(parent):
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
        if exists and type(parent[leaf]) not in scalar_types:
            return None
        if operation == "REMOVE":
            del parent[leaf]
        else:
            parent[leaf] = copy.deepcopy(mutation["value"])
    elif isinstance(parent, list):
        if not leaf.isascii() or not leaf.isdigit():
            return None
        offset = int(leaf)
        if operation == "ADD":
            if offset > len(parent):
                return None
            parent.insert(offset, copy.deepcopy(mutation["value"]))
        elif offset >= len(parent):
            return None
        elif type(parent[offset]) not in scalar_types:
            return None
        elif operation == "REMOVE":
            parent.pop(offset)
        else:
            parent[offset] = copy.deepcopy(mutation["value"])
    else:
        return None
    if not isinstance(mutated, dict) or canonical_wire_bytes(
        mutated
    ) == canonical_wire_bytes(positive):
        return None
    return mutated


def validate_semantic_corpus(
    content: bytes,
    identity: dict[str, Any],
    *,
    current_set: dict[str, Any],
    projection_payload: bytes,
    required_cases: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, bool], dict[str, dict[str, Any]], int]:
    corpus = load_json_bytes(
        content,
        identity["path"],
        maximum_bytes=MAX_JSON_BYTES,
    )
    if corpus.get("schema") != SEMANTIC_CORPUS_SCHEMA:
        fail("semantic closure corpus has an unknown schema")
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
    if not isinstance(cases, list) or not 1 <= len(cases) <= 256:
        fail("semantic closure corpus cases must contain 1..256 entries")
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
    satisfied: dict[str, bool] = {}
    case_expectations: dict[str, dict[str, Any]] = {}
    for case_id, requirement in required_cases.items():
        case = by_id.get(case_id)
        if not isinstance(case, dict):
            satisfied[case_id] = False
            continue
        common_keys = {
            "id",
            "source",
            "scope",
            "profile",
            "polarity",
            "expected_profile_result",
            "production_admission",
            "expected_diagnostics",
            "payload_interpreted",
        }
        expected_keys = set(common_keys)
        if requirement["kind"] == "HOSTILE":
            expected_keys.update(
                {
                    "positive_case_id",
                    "mutation_relation",
                    "mutation",
                }
            )
        diagnostics = case.get("expected_diagnostics")
        common = (
            set(case) == expected_keys
            and case.get("scope") == requirement["required_scope"]
            and case.get("profile") == requirement["required_profile"]
            and case.get("polarity") == requirement["required_polarity"]
            and case.get("expected_profile_result")
            == requirement["required_expected_profile_result"]
            and case.get("production_admission")
            == requirement["required_production_admission"]
            and case.get("payload_interpreted") is True
            and isinstance(diagnostics, list)
            and len(diagnostics) <= 32
            and len(diagnostics) == len(set(diagnostics))
            and all(
                isinstance(diagnostic, str) and CONDITION_ID.fullmatch(diagnostic)
                for diagnostic in diagnostics
            )
        )
        positive = bound_wire_object(
            case,
            requirement,
            case_path=f"semantic closure corpus case {case_id}",
        )
        wire_object = positive
        if requirement["kind"] == "POSITIVE":
            common = common and diagnostics == []
        else:
            positive_case = by_id.get(requirement["positive_case_id"])
            positive_requirement = required_cases[requirement["positive_case_id"]]
            bound_positive = (
                bound_wire_object(
                    positive_case,
                    positive_requirement,
                    case_path=(
                        "semantic closure corpus bound positive case "
                        f"{requirement['positive_case_id']}"
                    ),
                )
                if isinstance(positive_case, dict)
                else None
            )
            wire_object = (
                apply_single_wire_mutation(bound_positive, case.get("mutation"))
                if bound_positive is not None
                else None
            )
            common = common and (
                diagnostics != []
                and isinstance(positive_case, dict)
                and case.get("source") == positive_case.get("source")
                and case.get("positive_case_id") == requirement["positive_case_id"]
                and case.get("mutation_relation")
                == requirement["required_mutation_relation"]
            )
        common = common and positive is not None and wire_object is not None
        satisfied[case_id] = common
        if common:
            case_expectations[case_id] = {
                "input_sha256": sha256_bytes(canonical_wire_bytes(wire_object)),
                "profile_result": requirement["required_expected_profile_result"],
                "production_admission": requirement["required_production_admission"],
                "diagnostics": diagnostics,
            }
    binding_current = corpus.get("decision_set_binding") == (
        expected_corpus_decision_binding(current_set, projection_payload)
    )
    if not binding_current:
        return "STALE_DECISION_SET", satisfied, case_expectations, len(cases)
    if not all(satisfied.values()):
        return (
            "EXCERPTS_ONLY_NON_AUTHORIZING",
            satisfied,
            case_expectations,
            len(cases),
        )
    return "COMPLETE_CURRENT", satisfied, case_expectations, len(cases)


def evaluate_parser_result(
    *,
    engine: str,
    result_path: str,
    current_set: dict[str, Any],
    corpus_identity: dict[str, Any] | None,
    corpus_status: str,
    case_expectations: dict[str, dict[str, Any]],
    b03_expectations: list[dict[str, Any]],
    artifact_overrides: dict[str, bytes] | None,
    referenced_overrides: set[str],
    parser_runner: SemanticParserRunner,
) -> dict[str, Any]:
    observed = read_closure_artifact(
        result_path,
        artifact_overrides=artifact_overrides,
        referenced_overrides=referenced_overrides,
    )
    if observed is None:
        return {
            "engine": engine,
            "required_result_path": result_path,
            "required_status": "PASS",
            "observed_status": "NOT_RUN",
            "receipt": None,
            "execution": None,
        }
    identity, content = observed
    result = load_json_bytes(content, identity["path"])
    exact_keys(
        result,
        {*SEMANTIC_PARSER_RESULT_MEMBERS, "replay_receipt"},
        f"semantic parser result {engine}",
    )
    case_results = result["case_results"]
    if (
        not isinstance(case_results, list)
        or len(case_results) > 256
        or any(not isinstance(case_result, dict) for case_result in case_results)
    ):
        fail(f"semantic parser result {engine} has invalid case results")
    observed_case_results: dict[str, dict[str, Any]] = {}
    for index, case_result in enumerate(case_results):
        exact_keys(
            case_result,
            {
                "case_id",
                "input_sha256",
                "profile_result",
                "production_admission",
                "diagnostics",
            },
            f"semantic parser result {engine}.case_results[{index}]",
        )
        case_id = bounded_string(
            case_result["case_id"],
            f"semantic parser result {engine}.case_results[{index}].case_id",
            maximum=128,
        )
        if case_id in observed_case_results:
            fail(f"semantic parser result {engine} duplicates case {case_id}")
        observed_case_results[case_id] = case_result
    b03_results = result["b03_results"]
    if not isinstance(b03_results, list) or any(
        not isinstance(b03_result, dict) for b03_result in b03_results
    ):
        fail(f"semantic parser result {engine} has invalid B03 results")
    for index, b03_result in enumerate(b03_results):
        exact_keys(
            b03_result,
            {
                "question_id",
                "parameters",
                "identity_eligibility_universes",
            },
            f"semantic parser result {engine}.b03_results[{index}]",
        )
        eligibility_universes = b03_result["identity_eligibility_universes"]
        if not isinstance(eligibility_universes, list) or any(
            not isinstance(universe, dict) for universe in eligibility_universes
        ):
            fail(
                f"semantic parser result {engine}.b03_results[{index}] has "
                "invalid identity eligibility universes"
            )
        for universe_index, universe in enumerate(eligibility_universes):
            exact_keys(
                universe,
                {
                    "parameter_id",
                    "eligible_identities",
                    "eligible_identities_sha256",
                },
                (
                    f"semantic parser result {engine}.b03_results[{index}]."
                    f"identity_eligibility_universes[{universe_index}]"
                ),
            )
        parameters = b03_result["parameters"]
        if (
            not isinstance(parameters, list)
            or not 1 <= len(parameters) <= 16
            or any(not isinstance(parameter, dict) for parameter in parameters)
        ):
            fail(
                f"semantic parser result {engine}.b03_results[{index}] "
                "has invalid parameter results"
            )
        for parameter_index, parameter in enumerate(parameters):
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
                    "test_results",
                },
                (
                    f"semantic parser result {engine}.b03_results[{index}].parameters["
                    f"{parameter_index}]"
                ),
            )
            test_results = parameter["test_results"]
            if not isinstance(test_results, list) or any(
                not isinstance(test_result, dict) for test_result in test_results
            ):
                fail(
                    f"semantic parser result {engine}.b03_results[{index}]."
                    f"parameters[{parameter_index}] has invalid test results"
                )
            for test_index, test_result in enumerate(test_results):
                exact_keys(
                    test_result,
                    {"test_id", "status"},
                    (
                        f"semantic parser result {engine}.b03_results[{index}]."
                        f"parameters[{parameter_index}].test_results[{test_index}]"
                    ),
                )
    boundary = result["claim_boundary"]
    if (
        not isinstance(boundary, dict)
        or set(boundary)
        != {
            "adrs_accepted",
            "normative_contract_changed",
            "interoperability_established",
            "release_authorized",
        }
        or any(value is not False for value in boundary.values())
    ):
        fail(f"semantic parser result {engine} overclaims authority")
    if result["schema"] != SEMANTIC_PARSER_RESULT_SCHEMA or result["engine"] != engine:
        fail(f"semantic parser result {engine} has an unknown identity")
    if result["status"] not in {"PASS", "FAIL"}:
        fail(f"semantic parser result {engine} has an unknown status")
    replay_receipt = result["replay_receipt"]
    if replay_receipt is not None and not isinstance(replay_receipt, dict):
        fail(f"semantic parser result {engine} replay receipt is invalid")
    stale = (
        corpus_identity is None
        or corpus_status != "COMPLETE_CURRENT"
        or result["decision_set_sha256"] != current_set["sha256"]
        or result["corpus_sha256"] != corpus_identity["sha256"]
    )
    exact_results = (
        list(observed_case_results) == sorted(case_expectations)
        and b03_results == b03_expectations
    )
    if exact_results:
        for case_id, expectation in case_expectations.items():
            case_result = observed_case_results[case_id]
            if case_result != {
                "case_id": case_id,
                **expectation,
            }:
                exact_results = False
                break
    execution = None
    if stale:
        observed_status = "STALE"
    elif result["status"] != "PASS" or not exact_results:
        observed_status = "FAIL"
    elif replay_receipt is None:
        observed_status = "FAIL"
    else:
        validate_semantic_replay_receipt(replay_receipt, engine)
        replayed_content, observed_replay_receipt = parser_runner(engine)
        if not isinstance(observed_replay_receipt, dict):
            fail(f"direct {engine} semantic parser replay receipt is not an object")
        validate_semantic_replay_receipt(observed_replay_receipt, engine)
        replay_registry_sha256 = observed_replay_receipt.get(
            "derived_registry_binding", {}
        ).get("decision_set_sha256")
        if (
            replay_registry_sha256 != current_set["sha256"]
            or replay_registry_sha256 != result["decision_set_sha256"]
        ):
            fail(
                f"direct {engine} semantic replay registry binding differs "
                "from its evaluated decision set"
            )
        observed_after = read_closure_artifact(
            result_path,
            artifact_overrides=artifact_overrides,
            referenced_overrides=referenced_overrides,
        )
        if observed_after is None or observed_after != observed:
            fail(f"semantic parser result {engine} changed during direct replay")
        replayed_result = load_json_bytes(
            replayed_content,
            f"direct {engine} semantic parser replay",
        )
        semantic_projection = {
            member: result[member] for member in SEMANTIC_PARSER_RESULT_MEMBERS
        }
        if (
            replay_receipt is None
            or replayed_result != semantic_projection
            or replay_receipt != observed_replay_receipt
            or replay_receipt.get("stdout_sha256") != sha256_bytes(replayed_content)
            or replay_receipt.get("stdout_bytes") != len(replayed_content)
        ):
            observed_status = "FAIL"
        else:
            observed_status = "PASS"
            execution = copy.deepcopy(observed_replay_receipt)
    return {
        "engine": engine,
        "required_result_path": result_path,
        "required_status": "PASS",
        "observed_status": observed_status,
        "receipt": identity,
        "execution": execution,
    }


def evaluate_semantic_closure(
    requirements: dict[str, Any],
    generated: list[dict[str, Any]],
    source: dict[str, Any],
    current_policy: dict[str, Any],
    current_set: dict[str, Any],
    *,
    artifact_overrides: dict[str, bytes] | None = None,
    parser_runner: SemanticParserRunner = run_semantic_parser,
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
    wire_case_contract = requirements["source"]["wire_case_contract"]
    for closure in requirements["source"]["decisions"]:
        wire = closure["wire_requirements"]
        for case in wire["complete_positive"]:
            source_index = wire["required_source_paths"].index(case["source_path"])
            required_cases[case["case_id"]] = {
                **case,
                "kind": "POSITIVE",
                "decision_id": closure["id"],
                "source_identity": generated_by_id[closure["id"]]["source_set"][
                    "sources"
                ][source_index],
                "required_profile": (
                    f"{closure['id'].replace('-', '')}_SOURCE_{source_index + 1}_"
                    "COMPLETE_PROPOSED_WIRE_V1"
                ),
                "required_expected_profile_result": wire_case_contract[
                    "complete_positive"
                ]["expected_profile_result"],
                "required_production_admission": wire_case_contract[
                    "complete_positive"
                ]["production_admission"],
            }
        for case in wire["complete_hostile"]:
            source_index = wire["required_source_paths"].index(case["source_path"])
            required_cases[case["case_id"]] = {
                **case,
                "kind": "HOSTILE",
                "decision_id": closure["id"],
                "source_identity": generated_by_id[closure["id"]]["source_set"][
                    "sources"
                ][source_index],
                "required_profile": (
                    f"{closure['id'].replace('-', '')}_SOURCE_{source_index + 1}_"
                    "COMPLETE_PROPOSED_WIRE_V1"
                ),
                "required_expected_profile_result": wire_case_contract[
                    "complete_hostile"
                ]["expected_profile_result"],
                "required_production_admission": wire_case_contract["complete_hostile"][
                    "production_admission"
                ],
                "required_mutation_relation": wire_case_contract["complete_hostile"][
                    "mutation_relation"
                ],
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
        case_expectations: dict[str, dict[str, Any]] = {}
        case_count = 0
    else:
        corpus_identity, corpus_content = corpus_observed
        (
            corpus_status,
            case_satisfaction,
            case_expectations,
            case_count,
        ) = validate_semantic_corpus(
            corpus_content,
            corpus_identity,
            current_set=current_set,
            projection_payload=projection_payload,
            required_cases=required_cases,
        )
    b03_expectations: list[dict[str, Any]] = []
    b03_satisfaction: dict[str, bool] = {}
    for closure in requirements["source"]["decisions"]:
        for question in closure["questions"]:
            if question["state"] != "DEFERRED_B03":
                continue
            deferral = question["b03_deferral"]
            if deferral["validation_state"] != "VALIDATED":
                b03_satisfaction[question["question_id"]] = False
                continue
            parameter_expectations: list[dict[str, Any]] = []
            for parameter in deferral["parameters"]:
                parameter_expectations.append(
                    {
                        "parameter_id": parameter["parameter_id"],
                        "value_kind": parameter["value_kind"],
                        "selection_predicate_id": parameter["selection_predicate_id"],
                        "selection_predicate_source_anchor": parameter[
                            "selection_predicate_source_anchor"
                        ],
                        "selection_profile": parameter["selection_profile"],
                        "b03_selection_verifier_required": parameter[
                            "b03_selection_verifier_required"
                        ],
                        "inherits_excluded_no_edge_components": parameter[
                            "inherits_excluded_no_edge_components"
                        ],
                        "minimum": parameter["minimum"],
                        "maximum": parameter["maximum"],
                        "test_results": [
                            {"test_id": test_id, "status": "PASS"}
                            for test_id in parameter["required_tests"]
                        ],
                    }
                )
            b03_satisfaction[question["question_id"]] = True
            b03_expectations.append(
                {
                    "question_id": question["question_id"],
                    "identity_eligibility_universes": copy.deepcopy(
                        deferral["identity_eligibility_universes"]
                    ),
                    "parameters": parameter_expectations,
                }
            )
    rust_evidence = evaluate_parser_result(
        engine="RUST",
        result_path=RUST_PARSER_RESULT_PATH,
        current_set=current_set,
        corpus_identity=corpus_identity,
        corpus_status=corpus_status,
        case_expectations=case_expectations,
        b03_expectations=b03_expectations,
        artifact_overrides=artifact_overrides,
        referenced_overrides=referenced_overrides,
        parser_runner=parser_runner,
    )
    typescript_evidence = evaluate_parser_result(
        engine="TYPESCRIPT",
        result_path=TYPESCRIPT_PARSER_RESULT_PATH,
        current_set=current_set,
        corpus_identity=corpus_identity,
        corpus_status=corpus_status,
        case_expectations=case_expectations,
        b03_expectations=b03_expectations,
        artifact_overrides=artifact_overrides,
        referenced_overrides=referenced_overrides,
        parser_runner=parser_runner,
    )
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
        "wire_corpus": {
            "required_path": SEMANTIC_CORPUS_PATH,
            "required_status": "COMPLETE_CURRENT",
            "observed_status": corpus_status,
            "observed_identity": corpus_identity,
            "case_count": case_count,
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
        "capture_workflow": {
            "required_state": requirements["source"]["parser_replay_contract"][
                "capture_workflow_state"
            ],
            "observed_state": SEMANTIC_CAPTURE_WORKFLOW_STATE,
            "required_engine_profile_state": "IMPLEMENTED",
            "engine_profile_states": copy.deepcopy(
                requirements["source"]["parser_replay_contract"][
                    "engine_profile_states"
                ]
            ),
            "command": SEMANTIC_CAPTURE_COMMAND,
            "target_directory": SEMANTIC_CAPTURE_DIRECTORY,
            "write_policy": requirements["source"]["parser_replay_contract"][
                "capture_write_policy"
            ],
            "failure_effect": requirements["source"]["parser_replay_contract"][
                "capture_failure_effect"
            ],
        },
        "rust_parser_evidence": rust_evidence,
        "typescript_parser_evidence": typescript_evidence,
    }
    return public, {
        "case_satisfaction": case_satisfaction,
        "case_expectations": case_expectations,
        "b03_satisfaction": b03_satisfaction,
        "b03_expectations": b03_expectations,
        "corpus_identity": corpus_identity,
        "corpus_status": corpus_status,
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

    wire = closure["wire_requirements"]
    capture_workflow = evaluation["capture_workflow"]
    if capture_workflow["observed_state"] != capture_workflow["required_state"]:
        blockers.append(
            {
                "code": "SEMANTIC_PARSER_CAPTURE_NOT_IMPLEMENTED",
                "closure_id": f"{decision['id']}-PARSER-CAPTURE",
                "detail": (
                    "the exact dual-engine write-once parser-result capture "
                    "workflow is not implemented"
                ),
            }
        )
    for engine, profile_state in capture_workflow["engine_profile_states"].items():
        if profile_state != capture_workflow["required_engine_profile_state"]:
            blockers.append(
                {
                    "code": "SEMANTIC_PARSER_ENGINE_PROFILE_NOT_IMPLEMENTED",
                    "closure_id": f"{decision['id']}-{engine}-PROFILE",
                    "detail": (
                        f"the exact {engine} direct semantic parser capture profile "
                        "is not implemented; no retained result can close this gate"
                    ),
                }
            )
    if evaluation["wire_corpus"]["observed_status"] != "COMPLETE_CURRENT":
        blockers.append(
            {
                "code": "WIRE_EXAMPLE_CORPUS_NOT_CURRENT",
                "closure_id": f"{decision['id']}-WIRE-CORPUS",
                "detail": (
                    "the semantic corpus is missing, stale, or contains only "
                    "non-authorizing excerpts"
                ),
            }
        )
    case_satisfaction = observations["case_satisfaction"]
    for index, requirement in enumerate(wire["complete_positive"], start=1):
        if not case_satisfaction[requirement["case_id"]]:
            blockers.append(
                {
                    "code": "COMPLETE_POSITIVE_WIRE_EXAMPLE_MISSING",
                    "closure_id": f"{decision['id']}-WIRE-POSITIVE-{index}",
                    "detail": (
                        "the required source-bound complete positive proposed-wire "
                        f"case is absent: {requirement['case_id']}"
                    ),
                }
            )
    for index, requirement in enumerate(wire["complete_hostile"], start=1):
        if not case_satisfaction[requirement["case_id"]]:
            blockers.append(
                {
                    "code": "COMPLETE_HOSTILE_WIRE_EXAMPLE_MISSING",
                    "closure_id": f"{decision['id']}-WIRE-HOSTILE-{index}",
                    "detail": (
                        "the required one-semantic-delta hostile case is absent: "
                        f"{requirement['case_id']}"
                    ),
                }
            )
    for field, suffix in (
        ("rust_parser_evidence", "RUST-PARSER"),
        ("typescript_parser_evidence", "TYPESCRIPT-PARSER"),
    ):
        if evaluation[field]["observed_status"] != "PASS":
            blockers.append(
                {
                    "code": "WIRE_EXAMPLE_PARSER_NOT_PASSING",
                    "closure_id": f"{decision['id']}-{suffix}",
                    "detail": (
                        f"{evaluation[field]['engine']} parser evidence is not a "
                        "current complete-corpus PASS"
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
    fences = JSON_FENCE.findall(text)
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
    for index, fence in enumerate(JSON_FENCE.findall(text)):
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
    expected_main_prefix = f"docs/adr/{int(decision_id[-3:]):04d}-"
    expected_module_prefix = f"docs/adr/modules/{decision_id.lower()}-"
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
            if not relative.startswith(expected_main_prefix) or not relative.endswith(
                ".md"
            ):
                fail(f"{source_path}.path is not the matching ADR main Markdown")
        elif not relative.startswith(expected_module_prefix) or not relative.endswith(
            ".md"
        ):
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
        if not relative.startswith("docs/adr/") or not relative.endswith(".md"):
            fail(f"{path}.path must name an ADR Markdown file outside contract/")
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
        if (
            not isinstance(defects, list)
            or not 1 <= len(defects) <= 8
            or len(defects) != len(set(defects))
        ):
            fail(f"{path}.defect_ids must be 1..8 unique IDs")
        for defect in defects:
            if defect not in EXPECTED_DEFECTS:
                fail(f"{path}.defect_ids contains an unknown defect")
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
    fences = JSON_FENCE.findall(text)
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
    if lifecycle["state"] not in {"CURRENT", "SUPERSEDED", "TEMPLATE"}:
        fail("review_packet.lifecycle.state is invalid")
    if lifecycle["state"] == "CURRENT" and len(candidates) != 1:
        fail(
            "a CURRENT review packet requires exactly one machine-readable "
            "review-subject block"
        )
    if lifecycle["state"] != "CURRENT" and candidates:
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
    status = value["status"]
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
        adr_id = record["adr_id"]
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
        if reviewer["identity_kind"] not in {"PERSON", "TEAM"}:
            fail(f"{path}.reviewer.identity_kind must be PERSON or TEAM")
        if not isinstance(reviewer["independence_claimed"], bool):
            fail(f"{path}.reviewer.independence_claimed must be boolean")
        owners = reviewer["implementation_owner_identities"]
        if (
            not isinstance(owners, list)
            or not 1 <= len(owners) <= 32
            or len(owners) != len(set(owners))
        ):
            fail(
                f"{path}.reviewer.implementation_owner_identities must contain "
                "1..32 unique identities"
            )
        for owner_index, owner in enumerate(owners):
            validate_identity(
                owner,
                f"{path}.reviewer.implementation_owner_identities[{owner_index}]",
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
        decision = record["decision"]
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
    semantic_parser_runner: SemanticParserRunner = run_semantic_parser,
    subject_resolver: SubjectResolver = resolve_git_subject,
    policy_overrides: dict[str, bytes] | None = None,
    packet_override: bytes | None = None,
    closure_observation_sink: dict[str, Any] | None = None,
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
        parser_runner=semantic_parser_runner,
    )
    if closure_observation_sink is not None:
        if not isinstance(closure_observation_sink, dict):
            fail("semantic-closure observation sink must be a dictionary")
        closure_observation_sink.clear()
        closure_observation_sink.update(copy.deepcopy(closure_observations))
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
            closure_evaluation.get("wire_corpus", {}).get("observed_status")
            != "COMPLETE_CURRENT"
            or closure_evaluation.get("b03_deferrals", {}).get("observed_status")
            != "COMPLETE_ENVELOPES_VERIFIED"
            or closure_evaluation.get("capture_workflow", {}).get("required_state")
            != "IMPLEMENTED"
            or closure_evaluation.get("capture_workflow", {}).get("observed_state")
            != "IMPLEMENTED"
            or closure_evaluation.get("capture_workflow", {}).get(
                "required_engine_profile_state"
            )
            != "IMPLEMENTED"
            or set(
                closure_evaluation.get("capture_workflow", {})
                .get("engine_profile_states", {})
                .values()
            )
            != {"IMPLEMENTED"}
            or closure_evaluation.get("rust_parser_evidence", {}).get("observed_status")
            != "PASS"
            or not isinstance(
                closure_evaluation.get("rust_parser_evidence", {}).get("execution"),
                dict,
            )
            or closure_evaluation.get("typescript_parser_evidence", {}).get(
                "observed_status"
            )
            != "PASS"
            or not isinstance(
                closure_evaluation.get("typescript_parser_evidence", {}).get(
                    "execution"
                ),
                dict,
            )
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


def require_capture_target_absent(target_directory: Path) -> None:
    try:
        target_directory.lstat()
    except FileNotFoundError:
        return
    except OSError as error:
        fail(f"cannot inspect semantic capture target: {error}")
    fail(
        "semantic parser capture target already exists; write-once capture refuses "
        "to replace or merge retained results"
    )


def require_semantic_capture_engine_profiles() -> None:
    not_implemented = [
        engine
        for engine, state in SEMANTIC_ENGINE_PROFILE_STATES.items()
        if state != "IMPLEMENTED"
    ]
    if not_implemented:
        fail(
            "semantic parser capture engine profiles are NOT_IMPLEMENTED for "
            f"{','.join(not_implemented)}; wrote neither retained result"
        )


def atomic_rename_directory_no_replace(source: Path, target: Path) -> None:
    """Atomically install one directory without replacing an existing target."""

    source_bytes_path = os.fsencode(source)
    target_bytes_path = os.fsencode(target)
    libc = ctypes.CDLL(None, use_errno=True)
    if hasattr(libc, "renameat2"):
        renameat2 = libc.renameat2
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(
            -100,
            source_bytes_path,
            -100,
            target_bytes_path,
            1,
        )
    elif hasattr(libc, "renamex_np"):
        renamex_np = libc.renamex_np
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        result = renamex_np(source_bytes_path, target_bytes_path, 0x00000004)
    else:
        fail(
            "platform lacks an atomic no-replace directory rename primitive; "
            "wrote neither retained result"
        )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        fail(
            "semantic parser capture target already exists; write-once capture "
            "refuses to replace or merge retained results"
        )
    fail(
        "cannot atomically install semantic capture directory without replacement: "
        f"{os.strerror(error_number)}"
    )


def atomic_write_semantic_capture_results(
    results_by_path: dict[str, bytes],
    *,
    target_directory: Path,
    precommit_hook: Callable[[Path], None] | None = None,
) -> list[dict[str, Any]]:
    expected_paths = set(SEMANTIC_CAPTURE_RESULT_PATHS.values())
    if set(results_by_path) != expected_paths:
        fail(
            "semantic parser capture must stage exactly the Rust and TypeScript results"
        )
    expected_by_name: dict[str, bytes] = {}
    for repository_path, content in results_by_path.items():
        relative = relative_path(repository_path, "semantic capture result path")
        if PurePosixPath(relative).parent.as_posix() != SEMANTIC_CAPTURE_DIRECTORY:
            fail("semantic capture result path differs from the write-once directory")
        if type(content) is not bytes or not 1 <= len(content) <= MAX_JSON_BYTES:
            fail("semantic capture result must contain bounded native bytes")
        name = PurePosixPath(relative).name
        if name in expected_by_name:
            fail("semantic capture result filenames are not unique")
        expected_by_name[name] = content

    require_capture_target_absent(target_directory)
    parent = target_directory.parent
    missing_parents: list[Path] = []
    cursor = parent
    while True:
        try:
            metadata = cursor.lstat()
        except FileNotFoundError:
            missing_parents.append(cursor)
            next_cursor = cursor.parent
            if next_cursor == cursor:
                fail("semantic capture target has no existing physical ancestor")
            cursor = next_cursor
            continue
        except OSError as error:
            fail(f"cannot inspect semantic capture parent: {error}")
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            fail("semantic capture parent must be a physical directory")
        break

    created_parents: list[Path] = []
    staging: Path | None = None
    installed = False
    try:
        for directory in reversed(missing_parents):
            try:
                directory.mkdir(mode=0o700)
            except OSError as error:
                fail(f"cannot create semantic capture parent: {error}")
            created_parents.append(directory)
        try:
            staging = Path(
                tempfile.mkdtemp(
                    prefix=".ncp-b01-semantic-capture-",
                    dir=parent,
                )
            )
        except OSError as error:
            fail(f"cannot create semantic capture staging directory: {error}")

        for name, content in sorted(expected_by_name.items()):
            destination = staging / name
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                descriptor = os.open(destination, flags, 0o400)
            except OSError as error:
                fail(f"cannot create staged semantic capture result {name}: {error}")
            try:
                with os.fdopen(descriptor, "wb", closefd=False) as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError as error:
                fail(f"cannot write staged semantic capture result {name}: {error}")
            finally:
                os.close(descriptor)

        def validate_staging() -> None:
            if staging is None:
                fail("semantic capture staging directory is unavailable")
            try:
                entries = sorted(os.scandir(staging), key=lambda entry: entry.name)
            except OSError as error:
                fail(f"cannot inspect semantic capture staging directory: {error}")
            if [entry.name for entry in entries] != sorted(expected_by_name):
                fail("semantic capture staging directory has an unexpected file set")
            for entry in entries:
                try:
                    metadata = entry.stat(follow_symlinks=False)
                except OSError as error:
                    fail(f"cannot inspect staged semantic capture result: {error}")
                if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                    fail("staged semantic capture result is not a physical file")
                if stat.S_IMODE(metadata.st_mode) != 0o400:
                    fail("staged semantic capture result is not write-once read-only")
                try:
                    observed = read_bounded_regular_file(
                        staging / entry.name,
                        limits=REGISTRY_FILE_LIMITS,
                        label=f"staged semantic capture result {entry.name}",
                    )
                except BoundedJsonError as error:
                    fail(str(error))
                if observed != expected_by_name[entry.name]:
                    fail("staged semantic capture result bytes changed")

        validate_staging()
        if precommit_hook is not None:
            try:
                precommit_hook(staging)
            except RegistryError:
                raise
            except Exception as error:
                fail(f"semantic capture precommit hook failed: {error}")
            validate_staging()
        require_capture_target_absent(target_directory)
        try:
            stage_descriptor = os.open(staging, os.O_RDONLY)
            parent_descriptor = os.open(parent, os.O_RDONLY)
        except OSError as error:
            fail(f"cannot open semantic capture directory for synchronization: {error}")
        try:
            os.fsync(stage_descriptor)
            os.fsync(parent_descriptor)
        except OSError as error:
            fail(f"cannot synchronize semantic capture directory: {error}")
        finally:
            os.close(stage_descriptor)
            os.close(parent_descriptor)
        atomic_rename_directory_no_replace(staging, target_directory)
        installed = True
        staging = None
    finally:
        if staging is not None:
            try:
                shutil.rmtree(staging)
            except FileNotFoundError:
                pass
            except OSError:
                pass
        if not installed:
            for directory in reversed(created_parents):
                try:
                    directory.rmdir()
                except OSError:
                    pass

    return [
        {
            "path": path,
            "sha256": sha256_bytes(results_by_path[path]),
            "bytes": len(results_by_path[path]),
        }
        for path in SEMANTIC_CAPTURE_RESULT_PATHS.values()
    ]


def validate_semantic_capture_registry(
    expected: dict[str, Any], current_content: bytes
) -> None:
    if (
        type(current_content) is not bytes
        or not 1 <= len(current_content) <= MAX_JSON_BYTES
    ):
        fail("semantic capture registry input must contain bounded native bytes")
    current = load_json_bytes(
        current_content,
        OUTPUT.relative_to(ROOT).as_posix(),
    )
    try:
        validate_decision_registry_instance(current)
    except EvidenceSchemaError as error:
        fail(str(error))
    validate_generated(current, expected)
    if current_content != generated_bytes(expected):
        fail("semantic capture requires exact current generated registry bytes")

    evaluation = expected["semantic_closure_evaluation"]
    capture_workflow = evaluation["capture_workflow"]
    if (
        evaluation["state"] != "OPEN"
        or evaluation["wire_corpus"]["observed_status"] != "COMPLETE_CURRENT"
        or evaluation["b03_deferrals"]["observed_status"]
        != "COMPLETE_ENVELOPES_VERIFIED"
        or capture_workflow["required_state"] != "IMPLEMENTED"
        or capture_workflow["observed_state"] != "IMPLEMENTED"
        or capture_workflow["required_engine_profile_state"] != "IMPLEMENTED"
        or set(capture_workflow["engine_profile_states"].values()) != {"IMPLEMENTED"}
    ):
        fail(
            "semantic capture requires an exact OPEN registry with a complete "
            "current corpus, validated B03 deferral envelopes, and capture workflow"
        )
    for field, engine, result_path in (
        ("rust_parser_evidence", "RUST", RUST_PARSER_RESULT_PATH),
        (
            "typescript_parser_evidence",
            "TYPESCRIPT",
            TYPESCRIPT_PARSER_RESULT_PATH,
        ),
    ):
        evidence = evaluation[field]
        if evidence != {
            "engine": engine,
            "required_result_path": result_path,
            "required_status": "PASS",
            "observed_status": "NOT_RUN",
            "receipt": None,
            "execution": None,
        }:
            fail("semantic capture requires both parser results to be exactly NOT_RUN")
    for decision in expected["decisions"]:
        closure_blockers = [
            blocker
            for blocker in decision["acceptance_blockers"]
            if "closure_id" in blocker
        ]
        observed = [
            (blocker["code"], blocker["closure_id"]) for blocker in closure_blockers
        ]
        required = [
            ("SEMANTIC_CLOSURE_OPEN", "B01-SEMANTIC-CLOSURE"),
            (
                "WIRE_EXAMPLE_PARSER_NOT_PASSING",
                f"{decision['id']}-RUST-PARSER",
            ),
            (
                "WIRE_EXAMPLE_PARSER_NOT_PASSING",
                f"{decision['id']}-TYPESCRIPT-PARSER",
            ),
        ]
        if observed != required:
            fail(
                "semantic capture requires the two NOT_RUN parser artifacts to be "
                f"the only remaining {decision['id']} closure blockers"
            )


def validate_captured_semantic_result(
    *,
    engine: str,
    stdout: bytes,
    replay_receipt: dict[str, Any],
    registry: dict[str, Any],
    observations: dict[str, Any],
) -> bytes:
    result = load_json_bytes(stdout, f"direct {engine} semantic capture output")
    exact_keys(
        result,
        set(SEMANTIC_PARSER_RESULT_MEMBERS),
        f"direct {engine} semantic capture output",
    )
    retained = {**result, "replay_receipt": copy.deepcopy(replay_receipt)}
    retained_content = source_bytes(retained)
    result_path = SEMANTIC_CAPTURE_RESULT_PATHS[engine]

    def exact_replay(requested_engine: str) -> tuple[bytes, dict[str, Any]]:
        if requested_engine != engine:
            fail("semantic capture replay requested the wrong engine")
        return stdout, copy.deepcopy(replay_receipt)

    evaluated = evaluate_parser_result(
        engine=engine,
        result_path=result_path,
        current_set=registry["decision_set"],
        corpus_identity=observations["corpus_identity"],
        corpus_status=observations["corpus_status"],
        case_expectations=observations["case_expectations"],
        b03_expectations=observations["b03_expectations"],
        artifact_overrides={result_path: retained_content},
        referenced_overrides=set(),
        parser_runner=exact_replay,
    )
    if evaluated["observed_status"] != "PASS":
        fail(f"direct {engine} semantic capture did not validate as an exact PASS")
    return retained_content


def capture_semantic_parser_results(
    *,
    parser_runner: SemanticParserRunner = run_semantic_parser,
    current_registry_override: bytes | None = None,
    target_directory: Path | None = None,
) -> list[dict[str, Any]]:
    target = target_directory or ROOT.joinpath(
        *PurePosixPath(SEMANTIC_CAPTURE_DIRECTORY).parts
    )
    require_capture_target_absent(target)
    require_semantic_capture_engine_profiles()
    observations: dict[str, Any] = {}
    expected = build_registry(closure_observation_sink=observations)
    if current_registry_override is None:
        try:
            current_content = read_bounded_regular_file(
                OUTPUT,
                limits=REGISTRY_FILE_LIMITS,
                label=OUTPUT.relative_to(ROOT).as_posix(),
            )
        except BoundedJsonError as error:
            fail(str(error))
    else:
        current_content = current_registry_override
    validate_semantic_capture_registry(expected, current_content)

    retained_results: dict[str, bytes] = {}
    for engine in SEMANTIC_CAPTURE_RESULT_PATHS:
        try:
            stdout, replay_receipt = parser_runner(engine)
        except RegistryError as error:
            fail(
                f"{engine} semantic capture profile is NOT_IMPLEMENTED or failed: "
                f"{error}"
            )
        retained_results[SEMANTIC_CAPTURE_RESULT_PATHS[engine]] = (
            validate_captured_semantic_result(
                engine=engine,
                stdout=stdout,
                replay_receipt=replay_receipt,
                registry=expected,
                observations=observations,
            )
        )
    return atomic_write_semantic_capture_results(
        retained_results,
        target_directory=target,
    )


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
    with tempfile.TemporaryDirectory(prefix="ncp-b01-capture-self-test-") as root:
        capture_target = Path(root).resolve() / "nested" / "semantic-closure"
        runner_calls: list[str] = []

        def unexpected_capture_runner(engine: str) -> tuple[bytes, dict[str, Any]]:
            runner_calls.append(engine)
            raise AssertionError("NOT_IMPLEMENTED capture invoked a parser runner")

        try:
            capture_semantic_parser_results(
                parser_runner=unexpected_capture_runner,
                current_registry_override=generated_bytes(base),
                target_directory=capture_target,
            )
        except RegistryError as error:
            if str(error) != (
                "semantic parser capture engine profiles are NOT_IMPLEMENTED for "
                "RUST,TYPESCRIPT; wrote neither retained result"
            ):
                raise AssertionError(
                    "current semantic capture failed with a noncanonical diagnostic"
                ) from error
        else:
            raise AssertionError("NOT_IMPLEMENTED semantic capture unexpectedly passed")
        if runner_calls or capture_target.exists():
            raise AssertionError(
                "NOT_IMPLEMENTED semantic capture ran an engine or wrote a result"
            )

        staged_results = {
            RUST_PARSER_RESULT_PATH: b'{"engine":"RUST"}\n',
            TYPESCRIPT_PARSER_RESULT_PATH: b'{"engine":"TYPESCRIPT"}\n',
        }

        def reject_precommit(_staging: Path) -> None:
            fail("injected semantic capture precommit rejection")

        must_fail(
            lambda: atomic_write_semantic_capture_results(
                staged_results,
                target_directory=capture_target,
                precommit_hook=reject_precommit,
            ),
            "partial dual-result semantic capture installation",
        )
        if capture_target.exists():
            raise AssertionError(
                "failed semantic capture installed a partial directory"
            )
        captured_identities = atomic_write_semantic_capture_results(
            staged_results,
            target_directory=capture_target,
        )
        if [identity["path"] for identity in captured_identities] != list(
            SEMANTIC_CAPTURE_RESULT_PATHS.values()
        ):
            raise AssertionError(
                "semantic capture returned a noncanonical result order"
            )
        for repository_path, expected_content in staged_results.items():
            observed = (
                capture_target / PurePosixPath(repository_path).name
            ).read_bytes()
            if observed != expected_content:
                raise AssertionError("semantic capture changed retained result bytes")
        must_fail(
            lambda: atomic_write_semantic_capture_results(
                staged_results,
                target_directory=capture_target,
            ),
            "write-once semantic capture replacement",
        )

    stale_capture_registry = copy.deepcopy(base)
    stale_capture_registry["decision_set"]["sha256"] = "0" * 64
    must_fail(
        lambda: validate_semantic_capture_registry(
            base,
            generated_bytes(stale_capture_registry),
        ),
        "stale generated registry used for semantic capture",
    )
    if (
        any(decision["status"] == "ACCEPTED" for decision in base["decisions"])
        or base["review_records"]
    ):
        raise AssertionError("empty review source produced optimistic acceptance")
    if base["semantic_closure_evaluation"]["state"] != "OPEN":
        raise AssertionError("incomplete semantic closure did not remain OPEN")
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
    malformed_deferral["validation_state"] = "VALIDATED"
    malformed_deferral["parameters"][0].update({"minimum": 1, "maximum": 1})
    must_fail_closure_schema(
        malformed_schema_closure,
        "validated identity envelope with an empty eligibility universe",
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
    hostile_closure["decisions"][0]["adr_source_set_sha256"] = "0" * 64
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "stale ADR semantic closure binding",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["wire_case_contract"]["complete_positive"][
        "expected_profile_result"
    ] = "REJECT"
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "complete positive case whose required semantic result is REJECT",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["wire_case_contract"]["complete_positive"][
        "production_admission"
    ] = "ACCEPT"
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "complete positive case with optimistic production admission",
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
    ] = 1
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "OPEN B03 deferral with a fabricated literal bound",
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
    hostile_deferral = hostile_closure["decisions"][1]["questions"][0]["b03_deferral"]
    hostile_deferral["validation_state"] = "VALIDATED"
    hostile_parameter = hostile_deferral["parameters"][0]
    hostile_parameter["minimum"] = 0
    hostile_parameter["maximum"] = 0
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "vacuous zero-bound VALIDATED B03 parameter",
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
        "conformance/manifest.v1.json",
        "contract/manifest.v1.json",
    ]
    eligibility_universe["eligible_identities"] = eligible_identities
    eligibility_universe["eligible_identities_sha256"] = b03_eligibility_set_sha256(
        "ADR-002-Q01",
        "STABLE_CORE_FILE_IDENTITIES",
        eligible_identities,
    )
    validated_observations: dict[str, Any] = {}
    validated_envelope = build_registry(
        source,
        closure_source_override=hostile_closure,
        closure_observation_sink=validated_observations,
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
    hostile_closure["decisions"][3]["wire_requirements"]["complete_hostile"].pop()
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "ADR companion module without hostile direct-case coverage",
    )
    hostile_closure = copy.deepcopy(closure_source)
    hostile_closure["decisions"][0]["wire_requirements"]["complete_hostile"][0][
        "mutation_relation"
    ] = "MULTIPLE_SEMANTIC_DELTAS"
    must_fail(
        lambda: build_registry(source, closure_source_override=hostile_closure),
        "hostile proposed-wire case with multiple semantic deltas",
    )
    if (
        apply_single_wire_mutation(
            {"bounded": {"minimum": 0, "maximum": 1}},
            {"target": "DOCUMENT", "op": "REMOVE", "path": "/bounded"},
        )
        is not None
    ):
        raise AssertionError("one mutation removed a multi-field subtree")

    parser_expectations = {
        "adr001.complete-positive-wire.v1": {
            "input_sha256": "1" * 64,
            "profile_result": "MATCH_COMPLETE_NON_AUTHORIZING",
            "production_admission": "NOT_EVALUATED",
            "diagnostics": [],
        }
    }
    parser_b03_expectations = validated_observations["b03_expectations"]
    parser_result = {
        "schema": SEMANTIC_PARSER_RESULT_SCHEMA,
        "engine": "RUST",
        "decision_set_sha256": "2" * 64,
        "corpus_sha256": "3" * 64,
        "case_results": [
            {
                "case_id": "adr001.complete-positive-wire.v1",
                "input_sha256": "1" * 64,
                "profile_result": "REJECT",
                "production_admission": "ACCEPT",
                "diagnostics": [],
            }
        ],
        "b03_results": copy.deepcopy(parser_b03_expectations),
        "status": "PASS",
        "replay_receipt": None,
        "claim_boundary": {
            "adrs_accepted": False,
            "normative_contract_changed": False,
            "interoperability_established": False,
            "release_authorized": False,
        },
    }
    parser_control = evaluate_parser_result(
        engine="RUST",
        result_path=RUST_PARSER_RESULT_PATH,
        current_set={"sha256": "2" * 64},
        corpus_identity={"path": SEMANTIC_CORPUS_PATH, "sha256": "3" * 64, "bytes": 1},
        corpus_status="COMPLETE_CURRENT",
        case_expectations=parser_expectations,
        b03_expectations=parser_b03_expectations,
        artifact_overrides={RUST_PARSER_RESULT_PATH: source_bytes(parser_result)},
        referenced_overrides=set(),
        parser_runner=lambda _engine: (_ for _ in ()).throw(
            AssertionError("invalid parser result unexpectedly invoked its runner")
        ),
    )
    if parser_control["observed_status"] != "FAIL":
        raise AssertionError("parser PASS accepted swapped semantics or admission")

    exact_semantic_result = {
        member: copy.deepcopy(parser_result[member])
        for member in SEMANTIC_PARSER_RESULT_MEMBERS
    }
    exact_semantic_result["case_results"] = [
        {"case_id": case_id, **expectation}
        for case_id, expectation in sorted(parser_expectations.items())
    ]
    exact_semantic_result["b03_results"] = copy.deepcopy(parser_b03_expectations)
    deterministic_snapshot, deterministic_snapshot_contents = (
        semantic_replay_input_snapshot("RUST")
    )
    deterministic_public_snapshot = [
        identity
        for identity in deterministic_snapshot
        if identity["path"] not in SEMANTIC_REPLAY_DERIVED_INPUT_PATHS
    ]
    deterministic_registry_binding = semantic_replay_registry_binding(
        deterministic_snapshot_contents[OUTPUT.relative_to(ROOT).as_posix()]
    )
    replay_decision_set_sha256 = deterministic_registry_binding["decision_set_sha256"]
    exact_semantic_result["decision_set_sha256"] = replay_decision_set_sha256
    replayed_content = source_bytes(exact_semantic_result)
    deterministic_replay = {
        "schema": "ncp.b01-semantic-parser-replay.v1",
        "evidence_class": "OBSERVED_LOCAL_REPLAY_NOT_PROVENANCE",
        "command_profile": "RUST_CARGO_OFFLINE_LOCKED_CLOSURE_SELF_TEST_V1",
        "argv": semantic_parser_command_contract("RUST")[2],
        "working_directory": "TEMPORARY_BOUND_INPUT_SNAPSHOT_ROOT",
        "fixed_environment": copy.deepcopy(SEMANTIC_FIXED_ENVIRONMENT),
        "inherited_environment_keys": ["CARGO_HOME", "PATH", "RUSTUP_HOME"],
        "inherited_environment_sha256": sha256_bytes(b"self-test-environment"),
        "isolated_environment_keys": ["CARGO_TARGET_DIR", "HOME", "TMPDIR"],
        "isolated_cache_directory": True,
        "isolated_cache_environment_key": "CARGO_TARGET_DIR",
        "dependency_resolution_mode": "CARGO_OFFLINE_LOCKED",
        "process_network_isolation": "NOT_PROVIDED_LOCAL_REPLAY_ONLY",
        "dependency_cache_mode": "AMBIENT_CARGO_HOME_OFFLINE",
        "timeout_seconds": SEMANTIC_PARSER_TIMEOUT_SECONDS,
        "tools": [
            {
                "name": "cargo",
                "version": "cargo 1.88.0 (self-test)",
                "executable_sha256": "4" * 64,
                "executable_bytes": 1,
            },
            {
                "name": "rustc",
                "version": "rustc 1.88.0 (self-test)",
                "executable_sha256": "5" * 64,
                "executable_bytes": 1,
            },
        ],
        "engine_sources": semantic_engine_source_identities("RUST"),
        "repository_snapshot_inputs": deterministic_public_snapshot,
        "repository_snapshot_postcondition": "EXACT_FILE_SET_AND_BYTES_UNCHANGED",
        "derived_registry_binding": deterministic_registry_binding,
        "stdout_sha256": sha256_bytes(replayed_content),
        "stdout_bytes": len(replayed_content),
        "stderr_bytes": 0,
        "exit_code": 0,
        "source_tree_build_output_absent": True,
    }
    exact_result = {
        **exact_semantic_result,
        "replay_receipt": deterministic_replay,
    }
    exact_result_content = source_bytes(exact_result)
    replayed = evaluate_parser_result(
        engine="RUST",
        result_path=RUST_PARSER_RESULT_PATH,
        current_set={"sha256": replay_decision_set_sha256},
        corpus_identity={"path": SEMANTIC_CORPUS_PATH, "sha256": "3" * 64, "bytes": 1},
        corpus_status="COMPLETE_CURRENT",
        case_expectations=parser_expectations,
        b03_expectations=parser_b03_expectations,
        artifact_overrides={RUST_PARSER_RESULT_PATH: exact_result_content},
        referenced_overrides=set(),
        parser_runner=lambda _engine: (replayed_content, deterministic_replay),
    )
    if replayed["observed_status"] != "PASS":
        raise AssertionError("exact deterministic parser replay did not pass")
    for mutate_parser_eligibility, label in (
        (
            lambda universe: universe["eligible_identities"].__setitem__(
                0,
                "docs/adr/README.md",
            ),
            "substituted identity",
        ),
        (
            lambda universe: universe.update({"eligible_identities_sha256": "0" * 64}),
            "substituted eligibility digest",
        ),
    ):
        hostile_parser_result = copy.deepcopy(exact_result)
        mutate_parser_eligibility(
            hostile_parser_result["b03_results"][0]["identity_eligibility_universes"][0]
        )
        hostile_parser_control = evaluate_parser_result(
            engine="RUST",
            result_path=RUST_PARSER_RESULT_PATH,
            current_set={"sha256": replay_decision_set_sha256},
            corpus_identity={
                "path": SEMANTIC_CORPUS_PATH,
                "sha256": "3" * 64,
                "bytes": 1,
            },
            corpus_status="COMPLETE_CURRENT",
            case_expectations=parser_expectations,
            b03_expectations=parser_b03_expectations,
            artifact_overrides={
                RUST_PARSER_RESULT_PATH: source_bytes(hostile_parser_result)
            },
            referenced_overrides=set(),
            parser_runner=lambda _engine: (_ for _ in ()).throw(
                AssertionError("invalid B03 parser result invoked its runner")
            ),
        )
        if hostile_parser_control["observed_status"] != "FAIL":
            raise AssertionError(f"parser PASS accepted {label}")
    replay_schema_control = copy.deepcopy(base)
    rust_schema_evaluation = replay_schema_control["semantic_closure_evaluation"][
        "rust_parser_evidence"
    ]
    rust_schema_evaluation.update(
        {
            "observed_status": "PASS",
            "receipt": {
                "path": RUST_PARSER_RESULT_PATH,
                "sha256": "6" * 64,
                "bytes": 1,
            },
            "execution": deterministic_replay,
        }
    )
    validate_decision_registry_instance(replay_schema_control)
    for mutate_tool, label in (
        (
            lambda tool: tool.pop("version"),
            "missing required tool identity member",
        ),
        (
            lambda tool: tool.update({"unexpected": True}),
            "extra tool identity member",
        ),
    ):
        hostile_tool_identity = copy.deepcopy(replay_schema_control)
        mutate_tool(
            hostile_tool_identity["semantic_closure_evaluation"][
                "rust_parser_evidence"
            ]["execution"]["tools"][0]
        )
        try:
            validate_decision_registry_instance(hostile_tool_identity)
        except EvidenceSchemaError:
            pass
        else:
            raise AssertionError(f"output schema accepted {label}")
    typescript_snapshot, _ = semantic_replay_input_snapshot("TYPESCRIPT")
    hostile_cross_engine = copy.deepcopy(replay_schema_control)
    hostile_execution = hostile_cross_engine["semantic_closure_evaluation"][
        "rust_parser_evidence"
    ]["execution"]
    hostile_execution.update(
        {
            "command_profile": ("TYPESCRIPT_BUN_NO_INSTALL_CLOSURE_SELF_TEST_V1"),
            "argv": semantic_parser_command_contract("TYPESCRIPT")[2],
            "inherited_environment_keys": ["PATH"],
            "isolated_environment_keys": [
                "BUN_INSTALL_CACHE_DIR",
                "HOME",
                "TMPDIR",
            ],
            "isolated_cache_environment_key": "BUN_INSTALL_CACHE_DIR",
            "dependency_resolution_mode": "BUN_NO_INSTALL",
            "dependency_cache_mode": "NOT_USED_NO_INSTALL",
            "tools": [
                {
                    "name": "bun",
                    "version": "1.3.14",
                    "executable_sha256": "7" * 64,
                    "executable_bytes": 1,
                }
            ],
            "engine_sources": semantic_engine_source_identities("TYPESCRIPT"),
            "repository_snapshot_inputs": [
                identity
                for identity in typescript_snapshot
                if identity["path"] not in SEMANTIC_REPLAY_DERIVED_INPUT_PATHS
            ],
        }
    )
    try:
        validate_decision_registry_instance(hostile_cross_engine)
    except EvidenceSchemaError:
        pass
    else:
        raise AssertionError(
            "output schema accepted a TypeScript replay for the Rust engine gate"
        )
    fabricated_echo = evaluate_parser_result(
        engine="RUST",
        result_path=RUST_PARSER_RESULT_PATH,
        current_set={"sha256": replay_decision_set_sha256},
        corpus_identity={"path": SEMANTIC_CORPUS_PATH, "sha256": "3" * 64, "bytes": 1},
        corpus_status="COMPLETE_CURRENT",
        case_expectations=parser_expectations,
        b03_expectations=parser_b03_expectations,
        artifact_overrides={RUST_PARSER_RESULT_PATH: exact_result_content},
        referenced_overrides=set(),
        parser_runner=lambda _engine: (b'{"forged":false}\n', deterministic_replay),
    )
    if fabricated_echo["observed_status"] != "FAIL":
        raise AssertionError("fabricated parser echo bypassed direct replay")

    hostile_output = copy.deepcopy(base)
    hostile_output["semantic_closure_evaluation"]["state"] = "CLOSED"
    for parser_field in (
        "rust_parser_evidence",
        "typescript_parser_evidence",
    ):
        hostile_output["semantic_closure_evaluation"][parser_field][
            "observed_status"
        ] = "PASS"
    try:
        validate_decision_registry_instance(hostile_output)
    except EvidenceSchemaError:
        pass
    else:
        raise AssertionError(
            "output schema accepted CLOSED with stale corpus or null parser receipts"
        )

    forged_closed = copy.deepcopy(base)
    forged_evaluation = forged_closed["semantic_closure_evaluation"]
    forged_evaluation["state"] = "CLOSED"
    forged_evaluation["wire_corpus"]["observed_status"] = "COMPLETE_CURRENT"
    forged_evaluation["b03_deferrals"].update(
        {
            "validated_question_count": 7,
            "observed_status": "COMPLETE_ENVELOPES_VERIFIED",
        }
    )
    for parser_field in ("rust_parser_evidence", "typescript_parser_evidence"):
        parser_evaluation = forged_evaluation[parser_field]
        parser_evaluation["observed_status"] = "PASS"
        parser_evaluation["receipt"] = {
            "path": parser_evaluation["required_result_path"],
            "sha256": "1" * 64,
            "bytes": 1,
        }
    for decision in forged_closed["decisions"]:
        decision["status"] = "ACCEPTED"
    try:
        validate_decision_registry_instance(forged_closed)
    except EvidenceSchemaError:
        pass
    else:
        raise AssertionError(
            "output schema accepted blocked decisions under a forged CLOSED state"
        )

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
    open_reviewed_source = copy.deepcopy(source)
    requirements = open_reviewed_source["decisions"][0]["required_reviews"]
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
    open_reviewed_source["review_records"] = open_reviews
    open_reviewed = build_registry(
        open_reviewed_source,
        artifact_overrides=test_artifact_overrides(open_reviewed_source, content),
        subject_resolver=test_subject_resolver,
        packet_override=current_packet_content,
    )
    if open_reviewed["decisions"][0]["status"] != "PROPOSED":
        raise AssertionError("complete reviews bypassed OPEN semantic closure")
    if any(
        blocker["code"] in review_blocker_codes
        for blocker in open_reviewed["decisions"][0]["acceptance_blockers"]
    ):
        raise AssertionError("complete current reviews retained a review blocker")

    accepted_source = open_reviewed_source
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
            subject_resolver=test_resolver,
            policy_overrides=test_policy_overrides,
            packet_override=test_packet,
        )

    accepted = open_reviewed
    expected_override_source = source_bytes(accepted_source)
    if accepted["source"] != {
        "path": SOURCE_RELATIVE,
        "sha256": sha256_bytes(expected_override_source),
        "bytes": len(expected_override_source),
    }:
        raise AssertionError("source override identity does not bind override bytes")

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
    mode.add_argument(
        "--capture-semantic-parser-results",
        action="store_true",
        help=(
            "capture exact Rust and TypeScript semantic parser PASS results with "
            "a write-once atomic directory install"
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
        if args.capture_semantic_parser_results:
            if args.require_all_accepted:
                fail(
                    "semantic parser capture cannot be combined with "
                    "--require-all-accepted"
                )
            captured = capture_semantic_parser_results()
            print(
                "CAPTURED semantic parser results: "
                + ", ".join(identity["path"] for identity in captured)
            )
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
