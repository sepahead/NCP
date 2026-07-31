#!/usr/bin/env python3
"""Validate the compact, non-normative B01 selector-closure source."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import resource
import shlex
import signal
import subprocess
import sys
import tempfile
import tracemalloc
from collections.abc import Iterator
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from functools import partial
from hashlib import sha256
from heapq import heappop, heappush
from itertools import count, product
from pathlib import Path
from typing import Any, Callable, NoReturn

from selector_allocation_inventory import (
    ADR_ALLOCATION_ANCHOR_BY_ID,
    ADR_ALLOCATION_ANCHOR_IDS,
    ADR_ALLOCATION_MODULE_PATHS,
    ADR_ALLOCATION_PATHS,
    ADR_SOURCE_SET_SUITE,
    ALLOCATION_IDENTITY_COMMITMENT_SUITE,
    ALLOCATION_KIND_SET,
    ALLOCATION_KINDS,
    ALLOCATION_ORIGIN_KINDS,
    ALLOCATION_REVIEW_PROFILE_KEYS,
    ALLOCATION_REVIEW_PROFILE_SCHEMA,
    ALLOCATION_ROW_KEYS,
    ALLOCATION_SIGNAL_KINDS,
    DOCUMENT_KEYS,
    DOCUMENT_MODULE_KEYS,
    DOCUMENT_ROW_COMMITMENT,
    DOCUMENT_ROW_COMMITMENT_KEYS,
    DOCUMENT_SOURCE_SET_KEYS,
    EXCLUSION_CLASSIFICATIONS,
    EXCLUSION_ROW_KEYS,
    MAX_ADR_CORPUS_BYTES,
    MAX_ADR_DOCUMENT_BYTES,
    MAX_ALLOCATION_ROWS,
    MAX_ALLOCATION_SCHEMA_BYTES,
    MAX_SAFE_INTEGER,
    MAX_SEMANTIC_SHAPE_BYTES,
    MAX_SEMANTIC_SHAPE_DEPTH,
    MAX_SEMANTIC_SHAPE_POINTER_CHARS,
    MAX_SEMANTIC_SHAPE_ROWS,
    MODEL_ALLOCATION_PROJECTION_SCHEMA,
    MODEL_ORIGIN_SIGNAL_PROJECTION_SCHEMA,
    PROFILE_ID_SEMANTIC_REF,
    PROFILE_PATH_SEMANTIC_REF,
    PROFILE_REFERENCE_SEMANTIC_REF,
    PROVENANCE_REVIEW_KEYS,
    PROVENANCE_REVIEW_SUITE,
    RESOURCE_CLOSURE_PROJECTION_SCHEMA,
    RESOURCE_EXACT_NAME,
    RESOURCE_SEMANTIC_REF,
    SELECTOR_SEMANTIC_REF,
    SEMANTIC_REVIEW_SUBJECT_KEYS,
    SEMANTIC_REVIEW_SUBJECT_SUITE,
    SEMANTIC_SHAPE_COMMITMENT_SUITE,
    SEMANTIC_SHAPE_PROJECTION_DOMAIN,
    SEMANTIC_SHAPE_PROJECTION_SCHEMA,
    STATE_SEMANTIC_REF,
    adr_source_set_sha256,
    allocation_identity_projection,
    allocation_unit_id,
    build_not_reviewed_provenance_review,
    document_rows_sha256,
    model_allocation_projection_sha256,
    model_origin_signal_projection_commitment,
    provenance_assignment_sha256,
    semantic_review_subject_commitment,
)
from selector_closure_codec import (
    MAX_COMPACT_BYTES,
    MAX_EXPANDED_BYTES,
    MAX_TABLE_ITEMS,
    SelectorClosureCodecError,
    canonical_sha256,
    compact_selector_source,
    parse_json_bytes,
    read_bounded_regular_file,
    run_codec_self_test,
)
from selector_closure_codec import (
    canonical_bytes as codec_canonical_bytes,
)
from selector_closure_codec import (
    load_compact_source as codec_load_compact_source,
)
from selector_resource_closure import (
    RESOURCE_CLOSURE_KINDS,
    SUBORDINATE_HEAD_BACKINGS,
    ResourceClosureError,
    derive_resource_closure,
)
from selector_resource_closure import (
    run_self_test as run_resource_closure_self_test,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "docs" / "adr" / "selector-closure.source.v1.json"
SEMANTIC_ID = re.compile(r"^[A-Z][A-Z0-9_]*$")
EDGE_ID = re.compile(r"^E[0-9]{4,}$")
PARTITION_ID = re.compile(r"^P[0-9]{3,}$")
ALLOCATION_REF = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*::[A-Za-z0-9_]+$")
SEMANTIC_RESOURCE_REF = RESOURCE_EXACT_NAME
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
OPEN_QUESTIONS_HEADING = "## Open questions"
OPEN_QUESTIONS_HEADING_RE = re.compile(
    rf"(?m)^{re.escape(OPEN_QUESTIONS_HEADING)}[ \t]*\r?$"
)
NEXT_LEVEL_TWO_HEADING_RE = re.compile(r"(?m)^## [^\r\n]+")
ALLOCATION_ANCHOR_RE = re.compile(
    r'(?m)^[ \t]*<a[ \t]+id="'
    r"(ncp-b01-selector-allocation-adr-[0-9]{3}-v1)"
    r'"[ \t]*></a>[ \t]*\r?$'
)
BACKTICK_CODE_RE = re.compile(r"`+([^`]+?)`+", re.S)
HTML_CODE_RE = re.compile(r"(?is)<code(?:[ \t]+[^>]*)?>(.*?)</code[ \t]*>")
IDENTIFIER_TOKEN_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*\b")
ACCEPTED_ALLOCATION_PROSE_HEADINGS = {
    "Proposed decision",
    "Actors and state transitions",
    "Bounds and resource behavior",
    "Cross-store producer, audience, retention, and compromise rules",
    "External composite-state enrollment and retirement",
    "Formal properties",
    "Local namespace-closure import and prepared-intent resolution",
    "Operational recovery",
    "Source issuance and independent exposure-anchor closure",
}
ADR_ALLOCATION_KINDS = ALLOCATION_KIND_SET
ADR_EXCLUSION_CLASSIFICATIONS = EXCLUSION_CLASSIFICATIONS
BLOCKING_ADR_EXCLUSION_CLASSIFICATIONS = {"MODEL_OMISSION_FAIL_CLOSED"}
ALLOWED_EXTERNAL_ANCHOR_SECTION_TOKENS = frozenset({"ADR", "B01", "B03", "NCP"})
EXPECTED_MODEL_ALLOCATION_COUNT = 2_607
EXPECTED_MODEL_ALLOCATION_SHA256 = (
    "4bf942850f66c9cf951dc848502fe631cdc0a544b446643a53f72040b37702ee"
)
EXPECTED_MODEL_ORIGIN_SIGNAL_ROW_COUNT = 2_607
EXPECTED_MODEL_ORIGIN_SIGNAL_SHA256 = (
    "000603e4e80af52c30bbb3066db516e24a0f05d7e77944f3ffb80b7741afefd6"
)
EXPECTED_SEMANTIC_SHAPE_ENTRY_COUNT = 269_399
EXPECTED_SEMANTIC_SHAPE_SHA256 = (
    "1d70f5f61a993d376d3ed15b5813462beeccdbc3fe6ad7d93e46254948cb03ea"
)
EXTERNAL_COMPARE_RESOURCES: frozenset[str] = frozenset()
EXPECTED_RESOURCE_CLOSURE_PER_KIND_COUNTS = {
    "DEFINE": 392,
    "EFFECT": 1_782,
    "JTX_WRITE_PARTICIPANT": 30,
    "MUTATION_DERIVED": 1_364,
    "PROFILE_BINDING": 58,
}
EXPECTED_RESOURCE_CLOSURE_ROW_COUNT = 3_626

CANDIDATE_SELECTOR_ADR_SUGGESTION = {
    "ACTUATION_AUTHORITY_DOMAIN": "ADR-007",
    "AUTHORITY_REALM_ENROLLMENT_REGISTRY": "ADR-001",
    "AUTHORITY_TRANSACTION_DOMAIN": "ADR-001",
    "BODY_SESSION_CONTROL": "ADR-007",
    "CONSUMER_SEMANTIC_CAPTURE": "ADR-004",
    "CONSUMER_SURFACE_INVENTORY": "ADR-011",
    "GALADRIEL_LIFECYCLE": "ADR-008",
    "HALDIR_ASSESSMENT_RECEIVER": "ADR-008",
    "HALDIR_COMMANDER_PUBLICATION": "ADR-008",
    "HALDIR_POLICY": "ADR-008",
    "INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_REGISTRY": "ADR-004",
    "LOGICAL_SESSION_GENERATION_LINEAGE": "ADR-001",
    "LOGICAL_SESSION_NAMESPACE_REGISTRY": "ADR-001",
    "OBSERVER_ADMISSION": "ADR-004",
    "OBSERVER_ATTACHMENT_TARGET_HISTORY": "ADR-004",
    "OBSERVER_AUTHORIZATION": "ADR-004",
    "OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR": "ADR-004",
    "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX": "ADR-004",
    "OBSERVER_UNRESOLVED_TARGET_QUARANTINE": "ADR-004",
    "PHYSICAL_ACTUATION_JURISDICTION_ENROLLMENT_REGISTRY": "ADR-007",
    "PRISOMA_NUMERIC_EXECUTOR": "ADR-011",
    "RECEIVER_ADMISSION": "ADR-005",
    "SECURITY_AUTHORITY": "ADR-009",
    "SIMULATION_SESSION_STATE": "ADR-001",
    "TRUSTED_DELIVERY_RELEASE": "ADR-004",
}
CANDIDATE_PROFILE_ADR_SUGGESTION = {
    "actor_profiles": "ADR-011",
    "actuation_authority_domain_registry_profile": "ADR-007",
    "authority_realm_enrollment_registry_profile": "ADR-001",
    "authority_transaction_domain_profile": "ADR-001",
    "body_actuation_arbiter_profile": "ADR-007",
    "bulk_disposition_journal_profile": "ADR-007",
    "closed_event_profile_catalog": "ADR-001",
    "consumer_lifecycle_union_profile": "ADR-011",
    "deadline_linearization_profile": "ADR-006",
    "decision_relation_profile": "ADR-001",
    "forwarding_replay_profile": "ADR-003",
    "joint_selector_transaction_profiles": "ADR-001",
    "logical_session_generation_lineage_profile": "ADR-001",
    "logical_session_namespace_registry_profile": "ADR-001",
    "observer_grant_request_target_profile": "ADR-004",
    "observer_read_capture_bridge_profile": "ADR-004",
    "observer_unresolved_target_quarantine_profile": "ADR-004",
    "physical_actuation_jurisdiction_enrollment_profile": "ADR-007",
    "physical_actuation_jurisdiction_hardware_epoch_profile": "ADR-007",
    "realm_scoped_direct_binding_profile": "ADR-001",
    "security_authority_state_profile": "ADR-009",
    "selector_ownership_profile": "ADR-011",
    "sidecar_binding_profiles": "ADR-001",
    "simulation_session_state_profile": "ADR-001",
    "source_logical_session_retirement_profile": "ADR-001",
    "verification_model_profile": "ADR-001",
}
CANDIDATE_ADR001_JOINT_PROFILES = {
    "JTX_REQUIRED_CHILD_MARKER_CONSUMPTION_AT_BODY_SESSION_CONTROL_STATE_NATIVE_GENESIS",
    "JTX_REQUIRED_CHILD_MARKER_CONSUMPTION_AT_OBSERVER_AUTHORIZATION_STATE_NATIVE_GENESIS",
    "JTX_REQUIRED_CHILD_MARKER_CONSUMPTION_AT_SIMULATION_SESSION_STATE_NATIVE_GENESIS",
    "JTX_SOURCE_LINEAGE_REGISTRATION",
}
CANDIDATE_BODY_ADR006_STATE_DOMAINS = {
    "BODY_COMMAND_FRESHNESS_GRANT",
    "LEASE_CURRENTNESS",
    "LIFECYCLE_LATCH",
    "PENDING_AUTHORITY_OPERATION",
    "RETIREMENT_BOUNDARY_CLOSURE",
    "ROOT",
}
CANDIDATE_BODY_ADR006_TYPE_PREFIXES = (
    "BodyActuationBoundaryRetirementClosure",
    "BodyActuationDomainGenerationReconciliation",
    "BodyAuthorityDeadline",
    "BodyClockRestart",
    "BodyCommandFreshness",
    "BodyRetirementBoundaryClosure",
    "BodySessionGeneration",
    "ConfirmedEstop",
    "InstalledBodySessionControl",
    "PlantAuthority",
    "UnknownEstop",
)
CANDIDATE_BODY_CONTROL_ADR006_TYPE_FRAGMENTS = (
    "GenesisFact",
    "LeaseCurrentness",
    "LifecycleLatch",
    "PendingAuthorityOperation",
    "RetirementBoundaryClosure",
    "StateHead",
    "StateCommitReceipt",
    "StateSelector",
    "TransitionFact",
)
MAX_ADR_BYTES = MAX_ADR_DOCUMENT_BYTES
MAX_PROBE_SCRIPT_BYTES = 4 * 1024 * 1024
# Shared probe dependencies include the closed observer bridge profile. Keep this
# limit distinct from the executable-script limit and test both sides of it.
MAX_PROBE_DEPENDENCY_BYTES = 256 * 1024
MAX_PROBE_DEPENDENCIES = 3
MAX_PROBE_MODULE_NAME_BYTES = 128
MAX_PROBE_SOURCE_PATH_BYTES = 512
PROBE_FRAME_MAGIC = b"NCP-B01-PROBE-FRAME-V1\x00"
MAX_PROBE_INPUT_BYTES = (
    len(PROBE_FRAME_MAGIC)
    + 2
    + MAX_PROBE_DEPENDENCIES
    * (
        2
        + MAX_PROBE_MODULE_NAME_BYTES
        + 2
        + MAX_PROBE_SOURCE_PATH_BYTES
        + 4
        + MAX_PROBE_DEPENDENCY_BYTES
    )
    + 2
    + MAX_PROBE_SOURCE_PATH_BYTES
    + 4
    + MAX_PROBE_SCRIPT_BYTES
)
MAX_PROBE_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_PROBE_RSS_BYTES = 512 * 1024 * 1024
MAX_PROBE_OPEN_FILES = 64
MAX_PROBE_CPU_SECONDS = 900
MAX_PROBE_WALL_SECONDS = 1800
PROBE_SELF_TEST_CPU_SECONDS = 60
PROBE_SELF_TEST_WALL_SECONDS = 120
PROBE_LOADER_SOURCE = f"""
import os
import resource
import sys
import threading
import types

_MAGIC = {PROBE_FRAME_MAGIC!r}
_MAX_DEPENDENCIES = {MAX_PROBE_DEPENDENCIES}
_MAX_DEPENDENCY_BYTES = {MAX_PROBE_DEPENDENCY_BYTES}
_MAX_MODULE_NAME_BYTES = {MAX_PROBE_MODULE_NAME_BYTES}
_MAX_SOURCE_PATH_BYTES = {MAX_PROBE_SOURCE_PATH_BYTES}
_MAX_SCRIPT_BYTES = {MAX_PROBE_SCRIPT_BYTES}
_MAX_RSS_BYTES = {MAX_PROBE_RSS_BYTES}

if sys.platform == "darwin":
    _RSS_SCALE = 1
elif sys.platform.startswith("linux"):
    _RSS_SCALE = 1024
else:
    raise RuntimeError("unsupported ru_maxrss unit platform")

os.environ.clear()
_cwd = os.getcwd()
sys.path[:] = [entry for entry in sys.path if entry not in {{"", _cwd}}]


def _rss_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if type(value) not in {{int, float}} or value < 0:
        raise RuntimeError("invalid ru_maxrss value")
    return int(value) * _RSS_SCALE


def _enforce_rss():
    if _rss_bytes() > _MAX_RSS_BYTES:
        os._exit(75)


_stop = threading.Event()


def _watch_rss():
    while not _stop.wait(0.01):
        _enforce_rss()


_enforce_rss()
_watchdog = threading.Thread(
    target=_watch_rss,
    name="ncp-probe-rss-watchdog",
    daemon=True,
)
_watchdog.start()


def _read_exact(size):
    if type(size) is not int or size < 0:
        raise RuntimeError("invalid probe frame size")
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sys.stdin.buffer.read(size - len(chunks))
        if not chunk:
            raise RuntimeError("truncated probe frame")
        chunks.extend(chunk)
    return bytes(chunks)


def _read_u16():
    return int.from_bytes(_read_exact(2), "big")


def _read_u32():
    return int.from_bytes(_read_exact(4), "big")


def _read_text(maximum, encoding):
    size = _read_u16()
    if size == 0 or size > maximum:
        raise RuntimeError("probe frame text exceeds its bound")
    try:
        value = _read_exact(size).decode(encoding)
    except UnicodeError as error:
        raise RuntimeError("probe frame text is invalid") from error
    if "\\x00" in value:
        raise RuntimeError("probe frame text contains NUL")
    return value


try:
    if _read_exact(len(_MAGIC)) != _MAGIC:
        raise RuntimeError("probe frame magic differs")
    dependency_count = _read_u16()
    if dependency_count > _MAX_DEPENDENCIES:
        raise RuntimeError("probe dependency count exceeds its bound")
    module_names = set()
    dependency_sources = []
    for _index in range(dependency_count):
        module_name = _read_text(_MAX_MODULE_NAME_BYTES, "ascii")
        dependency_path = _read_text(_MAX_SOURCE_PATH_BYTES, "utf-8")
        source_size = _read_u32()
        if source_size == 0 or source_size > _MAX_DEPENDENCY_BYTES:
            raise RuntimeError("probe dependency bytes exceed their bound")
        if (
            not module_name.isidentifier()
            or module_name in module_names
            or module_name in sys.modules
        ):
            raise RuntimeError("probe dependency module name is invalid")
        module_names.add(module_name)
        source = _read_exact(source_size)
        dependency_sources.append((module_name, dependency_path, source))
    script_path = _read_text(_MAX_SOURCE_PATH_BYTES, "utf-8")
    script_size = _read_u32()
    if script_size == 0 or script_size > _MAX_SCRIPT_BYTES:
        raise RuntimeError("probe script bytes exceed their bound")
    script_source = _read_exact(script_size)
    if sys.stdin.buffer.read(1) != b"":
        raise RuntimeError("probe frame has trailing bytes")

    # Reject every framing, collision, and syntax failure before any bound source
    # executes. A malformed later field therefore cannot trigger an earlier
    # dependency side effect.
    dependency_code = [
        (
            module_name,
            dependency_path,
            compile(source, dependency_path, "exec", dont_inherit=True),
        )
        for module_name, dependency_path, source in dependency_sources
    ]
    script_code = compile(script_source, script_path, "exec", dont_inherit=True)
    _enforce_rss()
    for module_name, dependency_path, code in dependency_code:
        module = types.ModuleType(module_name)
        module.__file__ = dependency_path
        sys.modules[module_name] = module
        exec(code, module.__dict__)
        _enforce_rss()
    sys.argv[:] = [script_path]
    script_module = types.ModuleType("__main__")
    script_module.__file__ = script_path
    sys.modules["__main__"] = script_module
    exec(script_code, script_module.__dict__)
    _enforce_rss()
finally:
    _stop.set()
    _watchdog.join(timeout=1.0)
    _enforce_rss()
""".lstrip()
EXPECTED_PROBE_CLAIM_BOUNDARY = (
    "LOCAL_DETERMINISTIC_MODEL_EVIDENCE_ONLY_NOT_EXTERNAL_"
    "QUALIFICATION_CERTIFICATION_RELEASE_OR_PRODUCTION_EVIDENCE"
)
EXPECTED_PROBE_REVIEW_COMMANDS = {
    "freshness_acceptance_probe": (
        "python3 prototypes/b01-architecture-evidence/freshness_acceptance_probe.py"
    ),
    "observer_authorization_probe": (
        "python3 prototypes/b01-architecture-evidence/observer_authorization_probe.py"
    ),
    "observer_capture_probe": (
        "python3 prototypes/b01-architecture-evidence/observer_capture_probe.py"
    ),
    "source_issuance_index_probe": (
        "python3 prototypes/b01-architecture-evidence/source_issuance_index_probe.py"
    ),
}
EXPECTED_PROBE_SOURCE_PATHS = {
    probe_id: shlex.split(command)[1]
    for probe_id, command in EXPECTED_PROBE_REVIEW_COMMANDS.items()
}
EXPECTED_PROBE_CPU_SECONDS = {
    "freshness_acceptance_probe": 180,
    "observer_authorization_probe": 600,
    "observer_capture_probe": 900,
    "source_issuance_index_probe": 180,
}
EXPECTED_PROBE_WALL_SECONDS = {
    probe_id: cpu_seconds * 2
    for probe_id, cpu_seconds in EXPECTED_PROBE_CPU_SECONDS.items()
}
EXPECTED_PROBE_EXECUTION_PROFILE = {
    "claim_boundary": (
        "REVIEWED_EXACT_SOURCE_LOCAL_EVIDENCE_ONLY_"
        "NOT_AN_OS_SANDBOX_RUNTIME_PROVENANCE_OR_EXTERNAL_QUALIFICATION"
    ),
    "environment": "FIXED_LAUNCH_THEN_CLEARED_BEFORE_BOUND_SOURCE",
    "kernel_limits": {
        "core_bytes": 0,
        "cpu_seconds_by_probe": EXPECTED_PROBE_CPU_SECONDS,
        "file_bytes": MAX_PROBE_OUTPUT_BYTES,
        "inherited_limit_policy": (
            "PRESERVE_OR_TIGHTEN_EACH_INHERITED_SOFT_AND_HARD_LIMIT"
        ),
        "open_files": MAX_PROBE_OPEN_FILES,
    },
    "loader": "FIXED_LENGTH_FRAMED_IN_MEMORY_MODULE_LOADER_V1",
    "memory_boundary": {
        "enforcement": (
            "BEST_EFFORT_NORMALIZED_RU_MAXRSS_WATCHDOG_"
            "NOT_A_PROSPECTIVE_KERNEL_MEMORY_LIMIT"
        ),
        "maximum_rss_bytes": MAX_PROBE_RSS_BYTES,
    },
    "process_boundary": {
        "descendant_containment": (
            "NO_PROCESS_CREATION_DENIAL_AND_NEW_SESSION_DESCENDANTS_CAN_ESCAPE_"
            "PROCESS_GROUP_TERMINATION"
        ),
        "initial_child_session": "FRESH_PROCESS_SESSION",
        "launch_precondition": (
            "SINGLE_THREADED_POSIX_PARENT_FOR_PREEXEC_RESOURCE_LIMITS"
        ),
        "same_process_integrity": (
            "BOUND_CLASS_INSTANCE_MODULE_AND_CODE_STABILITY_IS_A_CALLER_"
            "OBLIGATION_WITH_NO_CONCURRENT_MUTATION"
        ),
        "side_effect_isolation": (
            "NO_NETWORK_FILESYSTEM_SYSCALL_OR_CHILD_PROCESS_SANDBOX"
        ),
    },
    "python_flags": ["-I", "-S", "-B", "-X", "utf8"],
    "runtime_provenance": (
        "INTERPRETER_STANDARD_LIBRARY_KERNEL_AND_DYNAMIC_RUNTIME_NOT_CONTENT_BOUND"
    ),
    "schema": "ncp.b01-bound-probe-execution-profile.v2",
    "source_limits": {
        "dependency_bytes_each": MAX_PROBE_DEPENDENCY_BYTES,
        "dependency_count": MAX_PROBE_DEPENDENCIES,
        "framed_input_bytes": MAX_PROBE_INPUT_BYTES,
        "module_name_bytes": MAX_PROBE_MODULE_NAME_BYTES,
        "output_bytes_each_channel": MAX_PROBE_OUTPUT_BYTES,
        "script_bytes": MAX_PROBE_SCRIPT_BYTES,
        "source_path_bytes": MAX_PROBE_SOURCE_PATH_BYTES,
    },
    "wall_clock_limits": {
        "policy": (
            "FINITE_EXACTLY_TWO_TIMES_CPU_FOR_SCHEDULER_SLACK_"
            "WITHOUT_INCREASING_CPU_AUTHORITY"
        ),
        "seconds_by_probe": EXPECTED_PROBE_WALL_SECONDS,
    },
    "working_directory": "FRESH_EMPTY_TEMPORARY_DIRECTORY",
}
EXPECTED_PROBE_BINDING_KEYS = {
    probe_id: {
        "dependency_ids",
        "review_command",
        "script_byte_length",
        "script_sha256",
        "source_path",
        "stdout_byte_length",
        "stdout_sha256",
    }
    for probe_id in EXPECTED_PROBE_REVIEW_COMMANDS
}
EXPECTED_PROBE_DEPENDENCIES = {
    "freshness_acceptance_probe": [],
    "observer_authorization_probe": [
        "bounded_canonical",
        "bounded_json",
        "observer_read_capture_bridge",
    ],
    "observer_capture_probe": [
        "bounded_canonical",
        "observer_read_capture_bridge",
    ],
    "source_issuance_index_probe": [],
}
EXPECTED_SHARED_PROBE_SOURCES = {
    "bounded_canonical": {
        "dependency_ids": [],
        "module": "bounded_canonical",
        "path": "prototypes/b01-architecture-evidence/bounded_canonical.py",
    },
    "bounded_json": {
        "dependency_ids": [],
        "module": "bounded_json",
        "path": "scripts/bounded_json.py",
    },
    "observer_read_capture_bridge": {
        "dependency_ids": ["bounded_canonical"],
        "module": "observer_read_capture_bridge",
        "path": (
            "prototypes/b01-architecture-evidence/observer_read_capture_bridge.py"
        ),
    },
}
OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_KAT = {
    "canonical_byte_length": 38_358,
    "canonical_sha256": (
        "77469e4604f38f811c61b9c7a4abd5227990e815387a27a3f7556215eb6b75c1"
    ),
    "digest": ("4226b60f52d799e36be6446d1069ed0d79efe910895f1ba6301ba949a49ded0a"),
    "digest_domain": "ncp.b01.bridge.ObserverReadCaptureBridgeProfileV2@1",
    "normalized_byte_length": 45_379,
    "normalized_sha256": (
        "7ddae8d9171ecd53d8306886d9ccbd9cdac2b5f2cda6578ddb00d4ffa3c7d56e"
    ),
    "schema": "ncp.b01-observer-read-capture-bridge-profile.v2",
}
OBSERVER_READ_CAPTURE_BRIDGE_SUITE_KAT = {
    "canonical_byte_length": 21_987,
    "canonical_sha256": (
        "b61cdc4657245335240b5a95362fd6942fbbce4cab824e3d0a0e65d4ddce37f0"
    ),
    "digest": ("92b1843fefd907cf30a1cfceb7fa251e2eb1ba46f3f47a68af4dfcf8d7608cf9"),
    "digest_domain": "ncp.b01.bridge.CanonicalCommitmentSuite@1",
    "normalized_byte_length": 26_972,
    "normalized_sha256": (
        "fd4b60114ef7b365da5d49ac00af52bdde044148affdcde7b815bfa4b55ce4b2"
    ),
    "schema": "ncp.b01.bridge-canonical-commitment-suite.v1",
}
OBSERVER_READ_CAPTURE_BRIDGE_COMMITMENT_FRAME_PREFIX = (
    b"NCP-B01-OBSERVER-READ-CAPTURE-BRIDGE-V1"
)


@dataclass(frozen=True, order=True)
class AllocationEvidence:
    """One stable mechanical origin or non-authoritative evidence signal."""

    evidence_kind: str
    semantic_location: str


@dataclass(frozen=True, order=True)
class ModelAllocation:
    """One owner-free semantic unit; evidence cannot affect identity or hashing."""

    kind: str
    exact_name: str
    semantic_ref: str
    unit_id: str = dataclass_field(init=False)
    origins: tuple[AllocationEvidence, ...] = dataclass_field(
        default=(),
        compare=False,
        hash=False,
    )
    signals: tuple[AllocationEvidence, ...] = dataclass_field(
        default=(),
        compare=False,
        hash=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_id",
            allocation_unit_id(self.kind, self.exact_name, self.semantic_ref),
        )

    def identity_row(self) -> list[str]:
        return allocation_identity_projection(
            self.kind,
            self.exact_name,
            self.semantic_ref,
        )

    def evidence_row(self) -> dict[str, Any]:
        return {
            "exact_name": self.exact_name,
            "kind": self.kind,
            "origins": [
                {
                    "evidence_kind": evidence.evidence_kind,
                    "semantic_location": evidence.semantic_location,
                }
                for evidence in self.origins
            ],
            "semantic_ref": self.semantic_ref,
            "signals": [
                {
                    "evidence_kind": evidence.evidence_kind,
                    "semantic_location": evidence.semantic_location,
                }
                for evidence in self.signals
            ],
            "unit_id": self.unit_id,
        }


class _AllocationAccumulator:
    """Aggregate evidence without letting evidence select semantic unit identity."""

    def __init__(self) -> None:
        self._entries: dict[
            tuple[str, str, str],
            tuple[set[AllocationEvidence], set[AllocationEvidence]],
        ] = {}

    def add(
        self,
        kind: str,
        exact_name: str,
        semantic_ref: str,
        *,
        origin: AllocationEvidence | None = None,
        signal: AllocationEvidence | None = None,
    ) -> None:
        key = (kind, exact_name, semantic_ref)
        origins, signals = self._entries.setdefault(key, (set(), set()))
        if origin is not None:
            require(
                origin.evidence_kind in ALLOCATION_ORIGIN_KINDS,
                f"unknown allocation origin kind {origin.evidence_kind}",
            )
            origins.add(origin)
        if signal is not None:
            require(
                signal.evidence_kind in ALLOCATION_SIGNAL_KINDS,
                f"unknown allocation signal kind {signal.evidence_kind}",
            )
            signals.add(signal)

    def include(self, allocation: ModelAllocation) -> None:
        for origin in allocation.origins:
            self.add(
                allocation.kind,
                allocation.exact_name,
                allocation.semantic_ref,
                origin=origin,
            )
        for evidence_signal in allocation.signals:
            self.add(
                allocation.kind,
                allocation.exact_name,
                allocation.semantic_ref,
                signal=evidence_signal,
            )

    def build(self) -> set[ModelAllocation]:
        model: set[ModelAllocation] = set()
        for (kind, exact_name, semantic_ref), (
            origins,
            signals,
        ) in self._entries.items():
            require(
                bool(origins),
                (
                    "allocation unit has only non-authoritative signals and no "
                    f"mechanical origin: {kind} {exact_name} {semantic_ref}"
                ),
            )
            model.add(
                ModelAllocation(
                    kind,
                    exact_name,
                    semantic_ref,
                    origins=tuple(sorted(origins)),
                    signals=tuple(sorted(signals)),
                )
            )
        return model


ExtractedIdentifier = tuple[str, str]

EXPANDED_TOP_LEVEL_KEYS = {
    "$schema",
    "actor_profiles",
    "actuation_authority_domain_registry_profile",
    "adr_allocation_oracle",
    "adversarial_probe_bindings",
    "allocation_boundary",
    "artifacts",
    "authority_realm_enrollment_registry_profile",
    "authority_transaction_domain_profile",
    "body_actuation_arbiter_profile",
    "bulk_disposition_journal_profile",
    "candidate",
    "claim_boundary",
    "closed_event_profile_catalog",
    "closure_commitments",
    "common_operation_dag",
    "consumer_lifecycle_union_profile",
    "deadline_linearization_profile",
    "decision_relation_profile",
    "forwarding_replay_profile",
    "generated_by",
    "generated_view",
    "global_key_coordinate_registry",
    "joint_selector_transaction_profiles",
    "logical_session_generation_lineage_profile",
    "logical_session_namespace_registry_profile",
    "normative",
    "observer_grant_request_target_profile",
    "observer_read_capture_bridge_profile",
    "observer_unresolved_target_quarantine_profile",
    "physical_actuation_jurisdiction_enrollment_profile",
    "physical_actuation_jurisdiction_hardware_epoch_profile",
    "pre_cas_variant_catalog",
    "realm_scoped_direct_binding_profile",
    "schema",
    "security_authority_state_profile",
    "selector_ownership_profile",
    "selectors",
    "sidecar_binding_profiles",
    "simulation_session_state_profile",
    "source_logical_session_retirement_profile",
    "task",
    "verification_model_profile",
}

SELECTOR_KEYS = {
    "events",
    "generic_receipt",
    "owned_resources",
    "owner",
    "root",
    "selector",
    "selector_id",
    "state_domains",
    "state_edge_catalog",
    "unknown_default_legacy_behavior",
}
OWNED_RESOURCE_KEYS = {
    "owner_selector_id",
    "resource",
}
COMMON_CASE_EFFECT_KEYS = {
    "action",
    "cardinality",
    "resource",
}
STATE_DOMAIN_KEYS = {
    "absence_semantics",
    "coordinate_alias_equalities",
    "foreign_key_equalities",
    "initial_state",
    "join_fields",
    "key_coordinates",
    "key_mode",
    "key_type",
    "owner_selector_id",
    "partition_owner",
    "resource_id",
    "root_terminal_safe_states",
    "root_terminal_safety_proof",
    "scope",
    "state_domain",
    "states",
    "terminal_states",
    "terminality",
}
STATE_DOMAIN_REQUIRED_KEYS = STATE_DOMAIN_KEYS - {
    "root_terminal_safe_states",
    "root_terminal_safety_proof",
}
STATE_EDGE_KEYS = {
    "edge_id",
    "entry_effect",
    "from_state",
    "key_cardinality",
    "key_mode",
    "key_ref",
    "preserve_siblings",
    "state_domain",
    "to_state",
}
EVENT_KEYS = {
    "actuation_domain_retirement_branch_partition",
    "arbiter_receipt_set_contract",
    "atomic_pre_cas_payloads",
    "authority_realm_registry_contract",
    "authority_transaction_contract",
    "authorization_status_witness",
    "bulk_disposition_journal_allocation",
    "candidate_constraints_profile_ref",
    "common_case_effects",
    "common_case_mutates",
    "consumes",
    "counter_effects",
    "creates",
    "cross_domain_guards",
    "deadline_conditions",
    "decision_model",
    "estop_result_reconciliation_contract",
    "event_id",
    "fail_safe_effect_selection",
    "fresh_native_participant_admission_contract",
    "guards_profile_ref",
    "interruption_resolutions_profile_ref",
    "joint_selector_transaction_profile_ref",
    "joint_selector_transaction_semantic_case_ids",
    "losing_cas_recovery",
    "lost_domain_external_cut_contract",
    "lost_domain_retirement_horizon_contract",
    "no_effect_precedence_profile_ref",
    "operation_commitment_profile_ref",
    "operation_scope",
    "partial_retirement_prepare_atomic_compare",
    "participant_admission_dependency_dag",
    "partition_effects",
    "physical_facility_registry_contract",
    "post_cas_sidecars",
    "pre_cas_content",
    "pre_genesis_tombstone_installation_contract",
    "preserves",
    "publication_remote_evidence_partition",
    "reattachment_origin_evidence_partition",
    "rejection_precedence_profile_ref",
    "replay_outcomes",
    "request_product_finalization_guard",
    "restrictive_selection_partition",
    "retirement_drain_contract",
    "retirement_finalization_evidence_partition",
    "security_serialization_profile_ref",
    "semantic_effects",
    "slot_realm_admission_contract",
    "source_lineage_registration_composite_contract",
    "state_loss_branch_contract",
    "subordinate_transition_application",
    "subordinate_transition_kinds",
    "transition_cases",
    "transition_kind",
    "transition_kind_state_domain",
    "version_effects_profile_ref",
}
EVENT_REQUIRED_KEYS = {
    "atomic_pre_cas_payloads",
    "candidate_constraints_profile_ref",
    "common_case_effects",
    "common_case_mutates",
    "consumes",
    "creates",
    "cross_domain_guards",
    "deadline_conditions",
    "decision_model",
    "event_id",
    "guards_profile_ref",
    "interruption_resolutions_profile_ref",
    "operation_commitment_profile_ref",
    "operation_scope",
    "partition_effects",
    "post_cas_sidecars",
    "pre_cas_content",
    "preserves",
    "security_serialization_profile_ref",
    "subordinate_transition_kinds",
    "transition_cases",
    "transition_kind",
    "transition_kind_state_domain",
    "version_effects_profile_ref",
}
TRANSITION_CASE_KEYS = {
    "case_contract",
    "evidence_variant_id",
    "semantic_case_id",
    "state_edge_refs",
}
CASE_CONTRACT_KEYS = {
    "actor_profile_ref",
    "common_nonstate_effects_from",
    "deadline_condition_ids",
    "deadline_set",
    "foreign_key_equalities_from",
    "partition_effect_refs",
    "sidecar_dag_from",
    "state_effects_from",
    "typed_key_binding_refs",
    "version_effects_from",
}
PARTITION_REQUIRED_KEYS = {
    "applies_to_semantic_case_ids",
    "bijection",
    "branches",
    "coverage",
    "empty_partitions",
    "key_type",
    "partition_id",
    "preserve_unlisted_keys",
    "state_domain",
}
PARTITION_KEYS = PARTITION_REQUIRED_KEYS | {
    "branch_cardinality_sum",
    "capacity_semantics",
    "cardinality_by_semantic_case",
    "complete_inventory_cardinality",
    "complete_required_role_set",
    "cross_branch_constraints",
    "cross_domain_bijection",
    "cross_partition_bijection",
    "exact_key_roles_by_branch",
    "forbidden_pre_cas_states",
    "forbidden_prior_states",
    "handoff_quiescence_bijection",
    "inventory_semantics",
    "journal_semantics_profile_ref",
    "logical_retention",
    "lost_state_rule",
    "mapping_closure",
    "missing_extra_duplicate_live_pending_or_authorizing_entry",
    "missing_extra_duplicate_or_nonterminal",
    "missing_extra_duplicate_or_wrong_generation",
    "missing_extra_duplicate_wrong_role_or_nonpristine",
    "nonapplicable_case_rule",
    "nonempty_partition",
    "pre_cas_journal_allocation",
    "preterminal_self_requirement",
    "prior_incarnation_rule",
    "request_kind_product_contract",
    "target_slot_effect",
    "total_cardinality",
    "unknown_duplicate_missing_or_extra_role",
    "unrelated_entries",
}
HANDOFF_QUIESCENCE_BIJECTION_KEYS = {
    "admitted_record_branch",
    "missing_duplicate_unknown_or_unproved_fence",
    "result_set_root",
    "rule",
}
PARTITION_BRANCH_KEYS = {
    "branch_id",
    "cardinality",
    "entry_effect",
    "from_state",
    "key_mode",
    "key_partition",
    "key_ref",
    "to_state",
    "version_effect",
}
REQUEST_KIND_PRODUCT_CONTRACT_KEYS = {
    "causal_outcome_source",
    "kind_field",
    "kind_source",
    "operation_edge_source",
    "outer_state_rule",
    "preserve_branch_kind_scopes",
    "resolution_rows",
    "unknown_missing_duplicate_or_cross_kind",
}
REQUEST_KIND_PRODUCT_RESOLUTION_ROW_KEYS = {
    "branch_id",
    "causal_outcome",
    "from_local_state",
    "g0_closure_requirement",
    "request_kind",
    "to_local_state",
}
REQUEST_KIND_PRODUCT_PRESERVE_SCOPE_KEYS = {
    "branch_id",
    "request_kinds",
}
REQUEST_PRODUCT_FINALIZATION_GUARD_KEYS = {
    "coverage",
    "operation_state_domain",
    "preservation",
    "required_exact_states",
    "unknown_missing_duplicate_or_nonterminal",
}
SIDECAR_REQUIRED_KEYS = {
    "artifact",
    "binding_profile_ref",
    "cardinality",
    "depends_on",
    "key_domain",
}
SIDECAR_KEYS = SIDECAR_REQUIRED_KEYS | {
    "additional_bindings",
    "additional_bindings_by_partition_branch",
    "additional_bindings_by_semantic_case",
    "applies_to_semantic_case_ids",
    "artifact_class",
    "dependency_class",
    "depends_on_by_semantic_case",
    "forbidden_bindings",
    "partition_branch_refs",
    "sidecar_type",
    "signature",
    "variant",
}
ARTIFACT_ITEM_KEYS = {
    "applies_to_semantic_case_ids",
    "artifact",
    "bound_by",
    "branch_condition",
    "constructed",
    "exposure",
    "persistence",
    "role",
}
AUTHORITY_PARTICIPANT_VARIANT_KEYS = {
    "participant_roles",
    "variant_id",
    "write_roles",
}
AUTHORITY_TRANSACTION_CONTRACT_KEYS = {
    "cas_condition",
    "commit_position",
    "common_field_equality",
    "derivation",
    "domain_key",
    "domain_state",
    "domain_state_participant",
    "failure",
    "forbidden_substitutes",
    "linearization",
    "lost_target_selector_participation",
    "participant_role_variants",
    "participant_set",
    "participant_set_entry_kinds",
    "participant_set_mode",
    "post_candidate_installed_state_sidecar",
    "pre_cas_semantic_commitment",
    "prior_installed_evidence_receipt",
    "qualification_receipt",
    "read_set",
    "receipt_dag",
    "role_universe",
    "semantic_commitment_scope",
    "static_role_policy_and_bounds",
    "store_incarnation",
    "write_roles",
    "write_roles_by_semantic_case",
}
AUTHORITY_TRANSACTION_CONTRACT_REQUIRED_KEYS = AUTHORITY_TRANSACTION_CONTRACT_KEYS - {
    "lost_target_selector_participation",
    "write_roles_by_semantic_case",
}
DEADLINE_CONDITIONS_KEYS = {
    "conditions",
    "families",
    "mode",
    "set_equality",
}
DECISION_MODEL_KEYS = {
    "admissible_relation_from",
    "axes",
    "common_required_fields",
    "event_id",
    "evidence_variant_definitions",
    "profile_ref",
    "selector_id",
}
DECISION_AXIS_REQUIRED_KEYS = {
    "axis_id",
    "derive_inputs",
    "derive_operator",
    "source_path",
    "trust_source",
    "type",
    "values_from",
}
DECISION_AXIS_KEYS = DECISION_AXIS_REQUIRED_KEYS | {
    "caller_supplied_case_or_target_label"
}
EVIDENCE_VARIANT_KEYS = {
    "evidence_variant_id",
    "forbidden_fields",
    "forbidden_fields_rule",
    "required_fields",
    "truth_conditions",
}
EVIDENCE_TRUTH_CONDITION_KEYS = {
    "field",
    "operator",
    "value",
}
NONTERMINAL_DOMAIN_POLICIES = {
    "PERSISTENT_FACILITY_INVENTORY",
    "PERSISTENT_HIGHER_AUTHORITY_REGISTRY",
    "PERSISTENT_LINEAGE_CHECKPOINT",
    "ROOT_OWNS_TERMINATION",
}
TERMINALITY_POLICIES = NONTERMINAL_DOMAIN_POLICIES | {
    "ALL_REACH_TERMINAL",
    "PERSISTENT_LINEAGE_ROOT",
    "PERSISTENT_REALM_REGISTRY",
    "PERSISTENT_TARGET_HISTORY",
}
OBSERVER_GRANT_REQUEST_KINDS = frozenset({"ATTACH", "REATTACH", "RENEW"})
OBSERVER_GRANT_PREPARED_INTENT_PERMANENT_RESOLUTION_CAUSES = frozenset(
    {
        "SOURCE_INDEX_FROZEN_NO_CHALLENGE",
        (
            "INDEPENDENT_EXPOSURE_ANCHOR_FROZEN_NONMEMBERSHIP_"
            "AFTER_SOURCE_TERMINAL_CLOSURE"
        ),
        (
            "INDEPENDENT_EXPOSURE_ANCHOR_FROZEN_MEMBERSHIP_ACCEPTANCE_"
            "PERMANENTLY_CLOSED_AFTER_SOURCE_TERMINAL_CLOSURE"
        ),
    }
)
OBSERVER_GRANT_REQUEST_CAUSAL_DISPOSITIONS = frozenset(
    {
        "ACCEPTED_TERMINAL_PENDING_AGGREGATES",
        "LIVE_RESPONSE",
        "NO_VERIFIED_SERVER_RESULT_YET",
        "PERMANENT_PREPARED_INTENT_RESOLUTION",
        "UNUSED_TERMINAL",
    }
)
OBSERVER_GRANT_REQUEST_CAUSAL_STATES = frozenset(
    {
        "ACCEPTED_TERMINAL_PENDING_AGGREGATES",
        "LIVE_RESPONSE",
        "NO_VERIFIED_SERVER_RESULT_YET",
        "SERVER_SLOT_CANCELED_UNUSED",
        "SERVER_SLOT_EXPIRED_UNUSED",
        *OBSERVER_GRANT_PREPARED_INTENT_PERMANENT_RESOLUTION_CAUSES,
    }
)
OBSERVER_GRANT_REQUEST_INITIAL_CAUSAL_STATE = "NO_VERIFIED_SERVER_RESULT_YET"
OBSERVER_GRANT_REQUEST_TERMINAL_RESOLUTION_CAUSES = frozenset(
    {
        "ACCEPTED_GRANT_FULLY_CLOSED_WITHOUT_LOCAL_INSTALLATION",
        "SERVER_SLOT_CANCELED_UNUSED",
        "SERVER_SLOT_EXPIRED_UNUSED",
    }
)
OBSERVER_GRANT_REQUEST_CAUSE_DISPOSITION = {
    "ACCEPTED_GRANT_FULLY_CLOSED_WITHOUT_LOCAL_INSTALLATION": (
        "ACCEPTED_TERMINAL_PENDING_AGGREGATES"
    ),
    "SERVER_SLOT_CANCELED_UNUSED": "UNUSED_TERMINAL",
    "SERVER_SLOT_EXPIRED_UNUSED": "UNUSED_TERMINAL",
}
OBSERVER_GRANT_REQUEST_RESOLUTION_CAUSE_STATE = {
    "ACCEPTED_GRANT_FULLY_CLOSED_WITHOUT_LOCAL_INSTALLATION": (
        "ACCEPTED_TERMINAL_PENDING_AGGREGATES"
    ),
    "SERVER_SLOT_CANCELED_UNUSED": "SERVER_SLOT_CANCELED_UNUSED",
    "SERVER_SLOT_EXPIRED_UNUSED": "SERVER_SLOT_EXPIRED_UNUSED",
}
OBSERVER_GRANT_REQUEST_CAUSE_FIELD = (
    "PRE_CAS_CONTENT.observer_grant_request_attempt_terminal_resolution_cause"
)
OBSERVER_GRANT_REQUEST_INTENT_CAUSE_FIELD = (
    "PRE_CAS_CONTENT.observer_grant_request_intent_terminal_resolution_cause"
)
OBSERVER_GRANT_REQUEST_EXACT_ATTEMPT_FIELD = (
    "PRE_CAS_CONTENT.exact_observer_grant_request_attempt"
)
OBSERVER_GRANT_REQUEST_EXACT_INTENT_FIELD = (
    "PRE_CAS_CONTENT.exact_observer_grant_request_intent"
)
OBSERVER_GRANT_REQUEST_VERIFICATION_FIELD = (
    "PRE_CAS_CONTENT.cross_store_security_receipt_verification_evidence"
)
CROSS_STORE_EXACT_OPERATION_VERIFICATION_OPERATOR = "VERIFIED_AND_BINDS_EXACT_OPERATION"
CROSS_STORE_PRODUCER_COMPLETION_MANIFEST_FIELD = (
    "PRE_CAS_CONTENT.cross_store_producer_bundle_completion_manifest"
)
CROSS_STORE_PROTECTED_OUTPUT_DELIVERY_CAPSULE_FIELD = (
    "PRE_CAS_CONTENT.cross_store_protected_output_delivery_capsule"
)
OBSERVER_GRANT_REQUEST_KIND_FIELD = "PRE_CAS_CONTENT.observer_grant_request_kind"
OBSERVER_GRANT_ACTIVATION_PUBLICATION_MANIFEST_FIELD = (
    "PRE_CAS_CONTENT.observer_grant_activation_publication_manifest"
)
OBSERVER_GRANT_ACTIVATION_PUBLICATION_MANIFEST_OPERATOR = (
    "VERIFIES_COMPLETE_ACTIVATION_PUBLICATION_MEMBERSHIP_AND_BIJECTION"
)
TRUSTED_DELIVERY_BOUNDARY_ACTIVATION_EVENT = "ACTIVATE_PREPARED_BOUNDARY_GRANT"
TRUSTED_DELIVERY_BOUNDARY_ACTIVATION_ENVELOPE_FIELD = (
    "PRE_CAS_CONTENT."
    "protected_trusted_delivery_boundary_grant_activation_decision_envelope"
)
TRUSTED_DELIVERY_BOUNDARY_ACTIVATION_MANIFEST_FIELD = (
    "PRE_CAS_CONTENT.trusted_delivery_boundary_grant_activation_publication_manifest"
)
TRUSTED_DELIVERY_BOUNDARY_ACTIVATION_MANIFEST_OPERATOR = (
    "VERIFIES_COMPLETE_BOUNDARY_ACTIVATION_PUBLICATION_MEMBERSHIP_AND_BIJECTION"
)
TRUSTED_DELIVERY_BOUNDARY_CLOSURE_MANIFEST_FIELD = (
    "PRE_CAS_CONTENT.trusted_delivery_boundary_closure_evidence_publication_manifest"
)
TRUSTED_DELIVERY_BOUNDARY_CLOSURE_MANIFEST_OPERATOR = (
    "VERIFIES_EXACT_BOUNDARY_CLOSURE_ENVELOPE_MEMBERSHIP"
)
TRUSTED_DELIVERY_BOUNDARY_CLOSURE_ENVELOPE_FIELD = (
    "PRE_CAS_CONTENT.protected_trusted_delivery_boundary_closure_evidence_envelope"
)
OBSERVER_GRANT_CLOSURE_AGGREGATION_EVENT = "ADVANCE_OBSERVER_GRANT_CLOSURE_AGGREGATION"
OBSERVER_GRANT_CLOSURE_AGGREGATION_DOMAIN = "GRANT_CLOSURE_AGGREGATION_MEMBER"
OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_KEY = (
    "observer-grant-closure-aggregation-member-key-type::"
    "ObserverGrantClosureAggregationMemberKey"
)
OBSERVER_GRANT_CLOSURE_AGGREGATION_HEAD = (
    "observer-grant-closure-aggregation-head-identity::"
    "ObserverGrantClosureAggregationHead"
)
OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_STATE = (
    "observer-grant-closure-aggregation-member-state-type::"
    "ObserverGrantClosureAggregationMemberState"
)
OBSERVER_GRANT_CLOSURE_AGGREGATION_OPERATION_KEY = (
    "observer-grant-closure-aggregation-operation-key-type::"
    "ObserverGrantClosureAggregationOperationKey"
)
OBSERVER_GRANT_CLOSURE_AGGREGATION_EVIDENCE_INPUT = (
    "observer-grant-closure-aggregation-evidence-input-type::"
    "ObserverGrantClosureAggregationEvidenceInput"
)
OBSERVER_GRANT_CLOSURE_AGGREGATION_EMPTY_UNIVERSE_PROOF = (
    "observer-grant-closure-aggregation-empty-universe-proof-type::"
    "ObserverGrantClosureAggregationEmptyUniverseProof"
)
OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_EVIDENCE_BIJECTION = (
    "observer-grant-closure-aggregation-member-evidence-bijection-type::"
    "ObserverGrantClosureAggregationMemberEvidenceBijection"
)
OBSERVER_GRANT_CLOSURE_AGGREGATION_OUTPUT_FIELD = (
    "PRE_CAS_CONTENT.observer_grant_closure_aggregate_output_class"
)
OBSERVER_GRANT_CLOSURE_AGGREGATION_AUTHORITY_EFFECT_FIELD = (
    "PRE_CAS_CONTENT.observer_grant_closure_aggregation_authority_effect"
)
OBSERVER_GRANT_CLOSURE_AGGREGATION_MARKER_EFFECT_FIELD = (
    "PRE_CAS_CONTENT.observer_role_marker_write_effect"
)
OBSERVER_GRANT_CLOSURE_AGGREGATION_EVIDENCE_INPUT_FIELD = (
    "PRE_CAS_CONTENT.observer_grant_closure_aggregation_evidence_input"
)
OBSERVER_GRANT_CLOSURE_AGGREGATION_EMPTY_UNIVERSE_PROOF_FIELD = (
    "PRE_CAS_CONTENT.observer_grant_closure_aggregation_empty_universe_proof"
)
OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_EVIDENCE_BIJECTION_FIELD = (
    "PRE_CAS_CONTENT.observer_grant_closure_aggregation_member_evidence_bijection"
)
OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_BIJECTION_OPERATOR = (
    "EXACT_AFFECTED_MEMBER_TO_NATIVE_EVIDENCE_UNION_BIJECTION_WITH_ONE_OR_MORE_"
    "MEMBERS_AND_EVERY_BOUNDARY_RETURN_ARM_VERIFIES_EXACT_ENVELOPE_FAMILY_"
    "COMPLETION_AND_BOTH_SCOPED_MEMBERSHIP_PROOFS"
)
OBSERVER_GRANT_CLOSURE_AGGREGATION_BOUNDARY_PUBLICATION_ARTIFACTS = frozenset(
    {
        (
            "cross-store-producer-bundle-completion-manifest-type::"
            "CrossStoreProducerBundleCompletionManifest"
        ),
        (
            "cross-store-protected-output-delivery-capsule-type::"
            "CrossStoreProtectedOutputDeliveryCapsule"
        ),
        (
            "cross-store-security-receipt-verification-evidence-type::"
            "CrossStoreSecurityReceiptVerificationEvidence"
        ),
        (
            "protected-trusted-delivery-boundary-closure-evidence-envelope-type::"
            "ProtectedTrustedDeliveryBoundaryClosureEvidenceEnvelope"
        ),
        (
            "trusted-delivery-boundary-closure-evidence-publication-manifest-type::"
            "TrustedDeliveryBoundaryClosureEvidencePublicationManifest"
        ),
    }
)
OBSERVER_GRANT_CLOSURE_AGGREGATION_OUTPUT_CLASSES = frozenset(
    {
        "AUTHORIZATION_CLOSED",
        "NO_COMPLETE_AGGREGATE",
        "TRANSPORT_QUIESCENT",
    }
)
OBSERVER_GRANT_CLOSURE_AGGREGATION_VARIANTS = {
    "AUTHORIZATION_CLOSED": (
        "MEMBER_ADVANCE_BATCH",
        "AUTHORIZATION_CLOSED",
    ),
    "NO_COMPLETE_AGGREGATE": (
        "MEMBER_ADVANCE_BATCH",
        "NO_COMPLETE_AGGREGATE",
    ),
    "TRANSPORT_QUIESCENT_EMPTY_UNIVERSE": (
        "EXACT_EMPTY_ACCEPTED_PLAN",
        "TRANSPORT_QUIESCENT",
    ),
    "TRANSPORT_QUIESCENT_NONEMPTY": (
        "MEMBER_ADVANCE_BATCH",
        "TRANSPORT_QUIESCENT",
    ),
}
OBSERVER_GRANT_CLOSURE_AGGREGATION_LATTICE_BRANCHES = {
    "UNOBSERVED_TO_AUTH_CLOSED_UNKNOWN": (
        "UNOBSERVED",
        "AUTH_CLOSED_UNKNOWN",
    ),
    "UNOBSERVED_TO_AUTH_CLOSED_EXACT": (
        "UNOBSERVED",
        "AUTH_CLOSED_EXACT",
    ),
    "AUTH_CLOSED_UNKNOWN_TO_AUTH_CLOSED_EXACT": (
        "AUTH_CLOSED_UNKNOWN",
        "AUTH_CLOSED_EXACT",
    ),
    "AUTH_CLOSED_EXACT_TO_TRANSPORT_QUIESCENT": (
        "AUTH_CLOSED_EXACT",
        "TRANSPORT_QUIESCENT",
    ),
}
OBSERVER_GRANT_CLOSURE_AGGREGATION_BRANCH_EFFECTS = {
    "UNOBSERVED_TO_AUTH_CLOSED_UNKNOWN": "MUTATE",
    "UNOBSERVED_TO_AUTH_CLOSED_EXACT": "MUTATE",
    "AUTH_CLOSED_UNKNOWN_TO_AUTH_CLOSED_EXACT": "MUTATE",
    "AUTH_CLOSED_EXACT_TO_TRANSPORT_QUIESCENT": "TOMBSTONE",
}
OBSERVER_GRANT_SOURCE_NAMESPACE_CLOSURE_IMPORT_EVENT = (
    "IMPORT_OBSERVER_GRANT_SOURCE_NAMESPACE_PERMANENT_CLOSURE"
)
OBSERVER_GRANT_REQUEST_FINALIZATION_EVENT = (
    "FINALIZE_OBSERVER_ADMISSION_SCOPE_RETIREMENT"
)
OBSERVER_GRANT_PERMANENT_RESOLUTION_CAUSE_BY_PARTITION_BRANCH = {
    "RESOLVE_PREPARED_SOURCE_NO_CHALLENGE": "SOURCE_INDEX_FROZEN_NO_CHALLENGE",
    "RESOLVE_PREPARED_ANCHOR_NONMEMBERSHIP": (
        "INDEPENDENT_EXPOSURE_ANCHOR_FROZEN_NONMEMBERSHIP_AFTER_SOURCE_TERMINAL_CLOSURE"
    ),
    "RESOLVE_PREPARED_ANCHOR_MEMBERSHIP_ACCEPTANCE_PERMANENTLY_CLOSED": (
        "INDEPENDENT_EXPOSURE_ANCHOR_FROZEN_MEMBERSHIP_ACCEPTANCE_"
        "PERMANENTLY_CLOSED_AFTER_SOURCE_TERMINAL_CLOSURE"
    ),
}
OBSERVER_GRANT_REQUEST_IMPORT_PRESERVE_BRANCH_STATES = {
    "PRESERVE_OPERATION_PHASE_PENDING_EXACT_TERMINAL_RESULT_PENDING_RESPONSE": (
        "PENDING_RESPONSE"
    ),
    "PRESERVE_OPERATION_PHASE_PENDING_EXACT_TERMINAL_RESULT_AMBIGUOUS": (
        "AMBIGUOUS_SERVER_ACCEPTANCE"
    ),
    "PRESERVE_RESOLVED_OR_INSTALLED_CLOSED_HISTORY_RESOLVED": (
        "RESOLVED_WITHOUT_INSTALLATION"
    ),
    "PRESERVE_RESOLVED_OR_INSTALLED_CLOSED_HISTORY_INSTALLED": "INSTALLED",
    "PRESERVE_INSTALLED_AWAITING_LOCAL_GRANT_CLOSURE": "INSTALLED",
    (
        "PRESERVE_OPERATION_PHASE_PENDING_EXACT_TERMINAL_RESULT_"
        "INTENT_PREPARED_CHALLENGE_ISSUED"
    ): "INTENT_PREPARED",
    (
        "PRESERVE_OPERATION_PHASE_PENDING_EXACT_TERMINAL_RESULT_"
        "OBSERVED_PENDING_CLOSURE"
    ): "TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE",
}
OBSERVER_GRANT_REQUEST_TERMINAL_OPERATION_STATES = frozenset(
    {
        "ABSENT",
        "INSTALLED",
        "RESOLVED_WITHOUT_INSTALLATION",
    }
)
OBSERVER_GRANT_REQUEST_UNUSED_EVIDENCE_FIELDS = frozenset(
    {
        "PRE_CAS_CONTENT.observer_grant_request_slot_terminal_publication_manifest",
        "PRE_CAS_CONTENT.protected_observer_grant_terminal_result_envelope",
        "PRE_CAS_CONTENT.source_freshness_registry_and_outer_heads_and_commits",
        "PRE_CAS_CONTENT.unused_request_slot_terminal_payload",
    }
)
OBSERVER_GRANT_REQUEST_ACCEPTED_CLOSURE_EVIDENCE_FIELDS = frozenset(
    {
        "PRE_CAS_CONTENT.local_noninstallation_and_no_frame_proof",
        "PRE_CAS_CONTENT.observer_grant_closure_result_publication_manifest",
        "PRE_CAS_CONTENT.observer_grant_distributed_authorization_closure_receipt",
        "PRE_CAS_CONTENT.observer_grant_transport_quiescence_receipt",
        "PRE_CAS_CONTENT.protected_observer_grant_closure_result_envelope",
    }
)
OBSERVER_GRANT_REQUEST_OBSERVATION_EVIDENCE_FIELDS = frozenset(
    {
        OBSERVER_GRANT_REQUEST_EXACT_ATTEMPT_FIELD,
        OBSERVER_GRANT_REQUEST_VERIFICATION_FIELD,
        "PRE_CAS_CONTENT.exact_accepted_server_slot_and_grant",
        "PRE_CAS_CONTENT.observer_grant_source_closure_publication_manifest",
        "PRE_CAS_CONTENT.protected_observer_grant_terminal_result_envelope",
        "PRE_CAS_CONTENT.source_grant_authorization_closure_decision",
    }
)
OBSERVER_GRANT_REQUEST_INSTALL_EVIDENCE_FIELDS = frozenset(
    {
        OBSERVER_GRANT_REQUEST_EXACT_ATTEMPT_FIELD,
        OBSERVER_GRANT_REQUEST_VERIFICATION_FIELD,
        "PRE_CAS_CONTENT.activation_guard_and_set_receipt",
        "PRE_CAS_CONTENT.exact_observer_target_bundle_and_projection",
        OBSERVER_GRANT_ACTIVATION_PUBLICATION_MANIFEST_FIELD,
        "PRE_CAS_CONTENT.protected_observer_grant_accepted_response_envelope",
        "PRE_CAS_CONTENT.server_and_observer_challenges",
        "PRE_CAS_CONTENT.source_live_heads_and_commits",
        "PRE_CAS_CONTENT.strict_deadline_evaluation_set",
    }
)
OBSERVER_GRANT_REQUEST_INSTALL_ADDITIONAL_EVIDENCE_FIELDS = {
    "INSTALL_OBSERVER_GRANT_FROM_ACCEPTED_RESPONSE": frozenset(),
    "INSTALL_OBSERVER_GRANT_REATTACHMENT_FROM_ACCEPTED_RESPONSE": (
        frozenset({"PRE_CAS_CONTENT.observer_grant_reattachment_origin_evidence"})
    ),
    "INSTALL_OBSERVER_GRANT_RENEWAL_FROM_ACCEPTED_RESPONSE": frozenset(
        {"PRE_CAS_CONTENT.exact_predecessor_closure_and_fence_evidence"}
    ),
}
OBSERVER_GRANT_REQUEST_INSTALL_EVENTS = frozenset(
    {
        "INSTALL_OBSERVER_GRANT_FROM_ACCEPTED_RESPONSE",
        "INSTALL_OBSERVER_GRANT_REATTACHMENT_FROM_ACCEPTED_RESPONSE",
        "INSTALL_OBSERVER_GRANT_RENEWAL_FROM_ACCEPTED_RESPONSE",
    }
)
OBSERVER_GRANT_REQUEST_RESOLVER_EVENTS = frozenset(
    {
        "RESOLVE_OBSERVER_GRANT_ATTACH_REQUEST_WITHOUT_INSTALLATION",
        "RESOLVE_OBSERVER_GRANT_REATTACH_REQUEST_WITHOUT_INSTALLATION",
        "RESOLVE_OBSERVER_GRANT_RENEWAL_WITHOUT_INSTALLATION",
    }
)
OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT = (
    "RESOLVE_OBSERVER_GRANT_REQUEST_INTENT_WITHOUT_CHALLENGE"
)
OBSERVER_GRANT_REQUEST_UNUSED_RESOLUTION_EVENTS = frozenset(
    {
        *OBSERVER_GRANT_REQUEST_RESOLVER_EVENTS,
        OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT,
    }
)
OBSERVER_GRANT_REQUEST_TERMINAL_OBSERVATION_EVENT = (
    "OBSERVE_OBSERVER_GRANT_TERMINAL_RESULT_PENDING_CLOSURE"
)
OBSERVER_GRANT_REQUEST_PREPARE_EVENT = "PREPARE_OBSERVER_GRANT_REQUEST_INTENT"
OBSERVER_GRANT_REQUEST_AMBIGUITY_EVENT = (
    "MARK_OBSERVER_GRANT_REQUEST_SERVER_ACCEPTANCE_AMBIGUOUS"
)
OBSERVER_GRANT_REQUEST_EVENT_KIND_SCOPE = {
    "BEGIN_OBSERVER_GRANT_ATTACH_REQUEST": frozenset({"ATTACH"}),
    "BEGIN_OBSERVER_GRANT_REATTACH_REQUEST": frozenset({"REATTACH"}),
    "BEGIN_OBSERVER_GRANT_RENEWAL_REQUEST": frozenset({"RENEW"}),
    "INSTALL_OBSERVER_GRANT_FROM_ACCEPTED_RESPONSE": frozenset({"ATTACH"}),
    "INSTALL_OBSERVER_GRANT_REATTACHMENT_FROM_ACCEPTED_RESPONSE": (
        frozenset({"REATTACH"})
    ),
    "INSTALL_OBSERVER_GRANT_RENEWAL_FROM_ACCEPTED_RESPONSE": frozenset({"RENEW"}),
    OBSERVER_GRANT_REQUEST_AMBIGUITY_EVENT: (OBSERVER_GRANT_REQUEST_KINDS),
    OBSERVER_GRANT_REQUEST_TERMINAL_OBSERVATION_EVENT: (OBSERVER_GRANT_REQUEST_KINDS),
    OBSERVER_GRANT_REQUEST_PREPARE_EVENT: (OBSERVER_GRANT_REQUEST_KINDS),
    OBSERVER_GRANT_SOURCE_NAMESPACE_CLOSURE_IMPORT_EVENT: (
        OBSERVER_GRANT_REQUEST_KINDS
    ),
    OBSERVER_GRANT_REQUEST_FINALIZATION_EVENT: OBSERVER_GRANT_REQUEST_KINDS,
    "RESOLVE_OBSERVER_GRANT_ATTACH_REQUEST_WITHOUT_INSTALLATION": (
        frozenset({"ATTACH"})
    ),
    "RESOLVE_OBSERVER_GRANT_REATTACH_REQUEST_WITHOUT_INSTALLATION": (
        frozenset({"REATTACH"})
    ),
    "RESOLVE_OBSERVER_GRANT_RENEWAL_WITHOUT_INSTALLATION": frozenset({"RENEW"}),
    OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT: (OBSERVER_GRANT_REQUEST_KINDS),
}
OBSERVER_GRANT_REQUEST_SHARED_KIND_EVENTS = frozenset(
    {
        OBSERVER_GRANT_REQUEST_AMBIGUITY_EVENT,
        OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT,
        OBSERVER_GRANT_REQUEST_PREPARE_EVENT,
        OBSERVER_GRANT_REQUEST_TERMINAL_OBSERVATION_EVENT,
    }
)
OBSERVER_GRANT_REQUEST_BEGIN_EVENTS = frozenset(
    {
        "BEGIN_OBSERVER_GRANT_ATTACH_REQUEST",
        "BEGIN_OBSERVER_GRANT_REATTACH_REQUEST",
        "BEGIN_OBSERVER_GRANT_RENEWAL_REQUEST",
    }
)
OBSERVER_GRANT_REQUEST_START_PRODUCT = {
    "ATTACH": ("PENDING_FIRST_ATTACH", "ABSENT"),
    "REATTACH": ("TERMINAL", "ABSENT"),
    "RENEW": ("LIVE", "ABSENT"),
}
OBSERVER_GRANT_REQUEST_SPLIT_START_PRODUCT = {
    kind: ("OPEN_ADMISSION", *state)
    for kind, state in OBSERVER_GRANT_REQUEST_START_PRODUCT.items()
}
OBSERVER_GRANT_REQUEST_SPLIT_PRODUCT_DOMAINS = (
    "OUTER_LIFECYCLE",
    "LOCAL_GRANT_STATE",
    "OBSERVER_GRANT_REQUEST_OPERATION_STATE",
)
OBSERVER_GRANT_REQUEST_SPLIT_DOMAIN_CONTRACT = {
    "OUTER_LIFECYCLE": {
        "initial_state": "PENDING_SOURCE_CONFIRMATION",
        "states": {
            "EMERGENCY_FENCED_CLOSURE_PENDING",
            "EMERGENCY_FENCED_RECOVERY_REQUIRED",
            "OPEN_ADMISSION",
            "PENDING_SOURCE_CONFIRMATION",
            "RETIRED_DRAIN_ONLY",
            "TERMINAL",
        },
        "terminality": "ALL_REACH_TERMINAL",
        "terminal_states": {"TERMINAL"},
    },
    "LOCAL_GRANT_STATE": {
        "initial_state": "PENDING_FIRST_ATTACH",
        "states": {
            "DETACH_PENDING",
            "LIVE",
            "LIVE_RENEW_PENDING",
            "PENDING_FIRST_ATTACH",
            "RENEW_PENDING_PREDECESSOR_CLOSED",
            "TERMINAL",
        },
        "root_terminal_safe_states": {"TERMINAL"},
        "terminality": "ROOT_OWNS_TERMINATION",
        "terminal_states": set(),
    },
    "OBSERVER_GRANT_REQUEST_OPERATION_STATE": {
        "initial_state": "ABSENT",
        "states": {
            "ABSENT",
            "AMBIGUOUS_SERVER_ACCEPTANCE",
            "INSTALLED",
            "INTENT_PREPARED",
            "PENDING_RESPONSE",
            "RESOLVED_WITHOUT_INSTALLATION",
            "TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE",
        },
        "terminality": "ALL_REACH_TERMINAL",
        "terminal_states": {
            "INSTALLED",
            "RESOLVED_WITHOUT_INSTALLATION",
        },
    },
}
OBSERVER_GRANT_REQUEST_RESOLUTION_OUTER_PHASES = frozenset(
    {
        "EMERGENCY_FENCED_CLOSURE_PENDING",
        "EMERGENCY_FENCED_RECOVERY_REQUIRED",
        "OPEN_ADMISSION",
        "RETIRED_DRAIN_ONLY",
    }
)
SHARED_TRANSITION_KIND_BY_EVENT = {
    event_id: "OBSERVER_GRANT_REGISTRY_TRANSITION"
    for event_id in {
        "ACTIVATE_PENDING_GRANT",
        "ATTACH_NEW_GRANT_LINEAGE",
        "BEGIN_GRANT_RENEWAL",
        "REATTACH_FROM_TERMINAL_GRANT",
        "TERMINATE_GRANT",
    }
}
SHARED_TRANSITION_KIND_BY_EVENT.update(
    {
        event_id: "OBSERVER_GRANT_REQUEST_FRESHNESS_TRANSITION"
        for event_id in {
            "CANCEL_OBSERVER_GRANT_REQUEST_BEFORE_ACCEPTANCE",
            "EXPIRE_OBSERVER_GRANT_REQUEST_BEFORE_ACCEPTANCE",
            "ISSUE_OBSERVER_GRANT_REQUEST_FRESHNESS_CHALLENGE",
        }
    }
)

EXPECTED_SELECTORS = {
    "ACTUATION_AUTHORITY_DOMAIN",
    "AUTHORITY_REALM_ENROLLMENT_REGISTRY",
    "AUTHORITY_TRANSACTION_DOMAIN",
    "BODY_SESSION_CONTROL",
    "CONSUMER_SEMANTIC_CAPTURE",
    "CONSUMER_SURFACE_INVENTORY",
    "GALADRIEL_LIFECYCLE",
    "HALDIR_ASSESSMENT_RECEIVER",
    "HALDIR_COMMANDER_PUBLICATION",
    "HALDIR_POLICY",
    "INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_REGISTRY",
    "LOGICAL_SESSION_GENERATION_LINEAGE",
    "LOGICAL_SESSION_NAMESPACE_REGISTRY",
    "OBSERVER_ADMISSION",
    "OBSERVER_ATTACHMENT_TARGET_HISTORY",
    "OBSERVER_AUTHORIZATION",
    "OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR",
    "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX",
    "OBSERVER_UNRESOLVED_TARGET_QUARANTINE",
    "PHYSICAL_ACTUATION_JURISDICTION_ENROLLMENT_REGISTRY",
    "PRISOMA_NUMERIC_EXECUTOR",
    "RECEIVER_ADMISSION",
    "SECURITY_AUTHORITY",
    "SIMULATION_SESSION_STATE",
    "TRUSTED_DELIVERY_RELEASE",
}


class ClosureCheckError(ValueError):
    """A selector-closure invariant failed."""


@dataclass(frozen=True)
class CheckSummary:
    selectors: int
    state_domains: int
    events: int
    semantic_cases: int
    partition_branches: int
    sidecars: int
    artifacts: int
    joint_transactions: int
    expanded_sha256: str


def fail(message: str) -> NoReturn:
    raise ClosureCheckError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def require_exact(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        fail(f"{label}: expected {expected!r}, got {actual!r}")


def require_unique(values: list[Any], label: str) -> None:
    canonical = [
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for value in values
    ]
    require(
        len(canonical) == len(set(canonical)),
        f"{label}: duplicate values",
    )


def require_acyclic_dependency_nodes(
    nodes: list[dict[str, Any]],
    label: str,
) -> dict[str, set[str]]:
    names = [node["node"] for node in nodes]
    require_unique(names, f"{label}: node identities")
    graph = {node["node"]: set(node["depends_on"]) for node in nodes}
    for node, dependencies in graph.items():
        require(
            node not in dependencies,
            f"{label}: {node} depends on itself",
        )
        require(
            dependencies.issubset(graph),
            f"{label}: {node} has undeclared dependencies "
            f"{sorted(dependencies - set(graph))}",
        )
    remaining = {node: set(dependencies) for node, dependencies in graph.items()}
    resolved: set[str] = set()
    while remaining:
        ready = sorted(
            node
            for node, dependencies in remaining.items()
            if dependencies.issubset(resolved)
        )
        require(ready, f"{label}: dependency cycle")
        resolved.update(ready)
        for node in ready:
            del remaining[node]
    return graph


def canonical_bytes(value: Any) -> bytes:
    return codec_canonical_bytes(value)


def load_compact_source(
    path: Path = DEFAULT_SOURCE,
    *,
    verify_round_trip: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        return codec_load_compact_source(
            path,
            verify_round_trip=verify_round_trip,
        )
    except SelectorClosureCodecError as error:
        fail(str(error))


def _require_compact_source_unchanged(
    path: Path,
    envelope: dict[str, Any],
) -> None:
    current = read_bounded_regular_file(
        path,
        maximum_bytes=MAX_COMPACT_BYTES - 1,
        label="compact selector source stability check",
    )
    require(
        current == canonical_bytes(envelope) + b"\n",
        "compact selector source changed during validation",
    )


def _require_closed_shape(
    value: Any,
    *,
    required: set[str],
    allowed: set[str],
    label: str,
) -> dict[str, Any]:
    require(isinstance(value, dict), f"{label}: expected an object")
    keys = set(value)
    require(
        required.issubset(keys),
        f"{label}: missing required properties {sorted(required - keys)}",
    )
    require(
        keys.issubset(allowed),
        f"{label}: unknown properties {sorted(keys - allowed)}",
    )
    return value


def _validate_closed_shapes(data: dict[str, Any]) -> None:
    require_exact(set(data), EXPANDED_TOP_LEVEL_KEYS, "expanded source keys")
    for selector_index, selector in enumerate(data["selectors"]):
        selector_label = f"selectors[{selector_index}]"
        _require_closed_shape(
            selector,
            required=SELECTOR_KEYS,
            allowed=SELECTOR_KEYS,
            label=selector_label,
        )
        for resource_index, owned_resource in enumerate(selector["owned_resources"]):
            _require_closed_shape(
                owned_resource,
                required=OWNED_RESOURCE_KEYS,
                allowed=OWNED_RESOURCE_KEYS,
                label=f"{selector_label}.owned_resources[{resource_index}]",
            )
        for domain_index, domain in enumerate(selector["state_domains"]):
            _require_closed_shape(
                domain,
                required=STATE_DOMAIN_REQUIRED_KEYS,
                allowed=STATE_DOMAIN_KEYS,
                label=f"{selector_label}.state_domains[{domain_index}]",
            )
        for edge_index, edge in enumerate(selector["state_edge_catalog"]):
            _require_closed_shape(
                edge,
                required=STATE_EDGE_KEYS,
                allowed=STATE_EDGE_KEYS,
                label=f"{selector_label}.state_edge_catalog[{edge_index}]",
            )
        for event_index, event in enumerate(selector["events"]):
            event_label = f"{selector_label}.events[{event_index}]"
            _require_closed_shape(
                event,
                required=EVENT_REQUIRED_KEYS,
                allowed=EVENT_KEYS,
                label=event_label,
            )
            _require_closed_shape(
                event["pre_cas_content"],
                required={
                    "artifact",
                    "forbidden_bindings",
                    "required_bindings",
                    "role",
                    "variant",
                },
                allowed={
                    "artifact",
                    "forbidden_bindings",
                    "required_bindings",
                    "role",
                    "variant",
                },
                label=f"{event_label}.pre_cas_content",
            )
            _require_closed_shape(
                event["decision_model"],
                required=DECISION_MODEL_KEYS,
                allowed=DECISION_MODEL_KEYS,
                label=f"{event_label}.decision_model",
            )
            for effect_index, effect in enumerate(event["common_case_effects"]):
                _require_closed_shape(
                    effect,
                    required=COMMON_CASE_EFFECT_KEYS,
                    allowed=COMMON_CASE_EFFECT_KEYS,
                    label=f"{event_label}.common_case_effects[{effect_index}]",
                )
            for axis_index, axis in enumerate(event["decision_model"]["axes"]):
                _require_closed_shape(
                    axis,
                    required=DECISION_AXIS_REQUIRED_KEYS,
                    allowed=DECISION_AXIS_KEYS,
                    label=(f"{event_label}.decision_model.axes[{axis_index}]"),
                )
            _require_closed_shape(
                event["deadline_conditions"],
                required=DEADLINE_CONDITIONS_KEYS,
                allowed=DEADLINE_CONDITIONS_KEYS,
                label=f"{event_label}.deadline_conditions",
            )
            finalization_guard = event.get("request_product_finalization_guard")
            if finalization_guard is not None:
                _require_closed_shape(
                    finalization_guard,
                    required=REQUEST_PRODUCT_FINALIZATION_GUARD_KEYS,
                    allowed=REQUEST_PRODUCT_FINALIZATION_GUARD_KEYS,
                    label=f"{event_label}.request_product_finalization_guard",
                )
            for variant_index, variant in enumerate(
                event["decision_model"]["evidence_variant_definitions"]
            ):
                _require_closed_shape(
                    variant,
                    required=EVIDENCE_VARIANT_KEYS,
                    allowed=EVIDENCE_VARIANT_KEYS,
                    label=(
                        f"{event_label}.decision_model."
                        f"evidence_variant_definitions[{variant_index}]"
                    ),
                )
                for condition_index, condition in enumerate(
                    variant["truth_conditions"]
                ):
                    _require_closed_shape(
                        condition,
                        required=EVIDENCE_TRUTH_CONDITION_KEYS,
                        allowed=EVIDENCE_TRUTH_CONDITION_KEYS,
                        label=(
                            f"{event_label}.decision_model."
                            "evidence_variant_definitions"
                            f"[{variant_index}].truth_conditions"
                            f"[{condition_index}]"
                        ),
                    )
            for case_index, transition_case in enumerate(event["transition_cases"]):
                case_label = f"{event_label}.transition_cases[{case_index}]"
                _require_closed_shape(
                    transition_case,
                    required=TRANSITION_CASE_KEYS,
                    allowed=TRANSITION_CASE_KEYS,
                    label=case_label,
                )
                _require_closed_shape(
                    transition_case["case_contract"],
                    required=CASE_CONTRACT_KEYS,
                    allowed=CASE_CONTRACT_KEYS,
                    label=f"{case_label}.case_contract",
                )
            for partition_index, partition in enumerate(event["partition_effects"]):
                partition_label = f"{event_label}.partition_effects[{partition_index}]"
                _require_closed_shape(
                    partition,
                    required=PARTITION_REQUIRED_KEYS,
                    allowed=PARTITION_KEYS,
                    label=partition_label,
                )
                handoff_bijection = partition.get("handoff_quiescence_bijection")
                if handoff_bijection is not None:
                    _require_closed_shape(
                        handoff_bijection,
                        required=HANDOFF_QUIESCENCE_BIJECTION_KEYS,
                        allowed=HANDOFF_QUIESCENCE_BIJECTION_KEYS,
                        label=(f"{partition_label}.handoff_quiescence_bijection"),
                    )
                request_kind_contract = partition.get("request_kind_product_contract")
                if request_kind_contract is not None:
                    _require_closed_shape(
                        request_kind_contract,
                        required=REQUEST_KIND_PRODUCT_CONTRACT_KEYS,
                        allowed=REQUEST_KIND_PRODUCT_CONTRACT_KEYS,
                        label=(f"{partition_label}.request_kind_product_contract"),
                    )
                    for row_index, row in enumerate(
                        request_kind_contract["resolution_rows"]
                    ):
                        _require_closed_shape(
                            row,
                            required=REQUEST_KIND_PRODUCT_RESOLUTION_ROW_KEYS,
                            allowed=REQUEST_KIND_PRODUCT_RESOLUTION_ROW_KEYS,
                            label=(
                                f"{partition_label}."
                                "request_kind_product_contract.resolution_rows"
                                f"[{row_index}]"
                            ),
                        )
                    for scope_index, scope in enumerate(
                        request_kind_contract["preserve_branch_kind_scopes"]
                    ):
                        _require_closed_shape(
                            scope,
                            required=REQUEST_KIND_PRODUCT_PRESERVE_SCOPE_KEYS,
                            allowed=REQUEST_KIND_PRODUCT_PRESERVE_SCOPE_KEYS,
                            label=(
                                f"{partition_label}."
                                "request_kind_product_contract."
                                f"preserve_branch_kind_scopes[{scope_index}]"
                            ),
                        )
                for branch_index, branch in enumerate(partition["branches"]):
                    _require_closed_shape(
                        branch,
                        required=PARTITION_BRANCH_KEYS,
                        allowed=PARTITION_BRANCH_KEYS,
                        label=(f"{partition_label}.branches[{branch_index}]"),
                    )
            for sidecar_index, sidecar in enumerate(event["post_cas_sidecars"]):
                _require_closed_shape(
                    sidecar,
                    required=SIDECAR_REQUIRED_KEYS,
                    allowed=SIDECAR_KEYS,
                    label=f"{event_label}.post_cas_sidecars[{sidecar_index}]",
                )
            for collection_name in (
                "consumes",
                "creates",
                "atomic_pre_cas_payloads",
            ):
                for item_index, item in enumerate(event[collection_name]):
                    _require_closed_shape(
                        item,
                        required={"artifact"},
                        allowed=ARTIFACT_ITEM_KEYS,
                        label=(f"{event_label}.{collection_name}[{item_index}]"),
                    )
            contract = event.get("authority_transaction_contract")
            if contract is not None:
                _require_closed_shape(
                    contract,
                    required=AUTHORITY_TRANSACTION_CONTRACT_REQUIRED_KEYS,
                    allowed=AUTHORITY_TRANSACTION_CONTRACT_KEYS,
                    label=f"{event_label}.authority_transaction_contract",
                )
                for variant_index, variant in enumerate(
                    contract["participant_role_variants"]
                ):
                    _require_closed_shape(
                        variant,
                        required=AUTHORITY_PARTICIPANT_VARIANT_KEYS,
                        allowed=AUTHORITY_PARTICIPANT_VARIANT_KEYS,
                        label=(
                            f"{event_label}.authority_transaction_contract."
                            f"participant_role_variants[{variant_index}]"
                        ),
                    )


def _validate_owned_resource_registry(data: dict[str, Any]) -> None:
    """Close every local effect and mutation over one exact owner registry."""

    registry: dict[str, str] = {}
    for selector_index, selector in enumerate(data["selectors"]):
        selector_label = f"selectors[{selector_index}]"
        selector_id = selector["selector_id"]
        resources = selector["owned_resources"]
        require(
            isinstance(resources, list),
            f"{selector_label}.owned_resources must be an array",
        )
        resource_order: list[tuple[str, str]] = []
        for resource_index, declaration in enumerate(resources):
            label = f"{selector_label}.owned_resources[{resource_index}]"
            owner = declaration["owner_selector_id"]
            resource = declaration["resource"]
            require_exact(owner, selector_id, f"{label}: owner selector")
            require(
                isinstance(resource, str)
                and SEMANTIC_RESOURCE_REF.fullmatch(resource) is not None,
                f"{label}: invalid semantic resource identity",
            )
            require(
                resource.startswith(f"{selector_id}."),
                f"{label}: resource is outside its selector namespace",
            )
            require(
                resource not in registry,
                (f"{label}: resource is already owned by {registry.get(resource)}"),
            )
            registry[resource] = selector_id
            resource_order.append((owner, resource))
        require_exact(
            resource_order,
            sorted(resource_order),
            f"{selector_label}: owned resource order",
        )

        declared_state_domain_resources = {
            resource
            for resource in registry
            if resource.startswith(f"{selector_id}.STATE_DOMAIN.")
        }
        expected_state_domain_resources = {
            f"{selector_id}.STATE_DOMAIN.{domain['state_domain']}"
            for domain in selector["state_domains"]
        }
        require_exact(
            declared_state_domain_resources,
            expected_state_domain_resources,
            f"{selector_label}: state-domain resource registry",
        )

    require(bool(registry), "owned resource registry is empty")
    for selector_index, selector in enumerate(data["selectors"]):
        for event_index, event in enumerate(selector["events"]):
            event_label = f"selectors[{selector_index}].events[{event_index}]"
            effects = event["common_case_effects"]
            mutations = event["common_case_mutates"]
            require(
                isinstance(effects, list),
                f"{event_label}.common_case_effects must be an array",
            )
            require(
                isinstance(mutations, list),
                f"{event_label}.common_case_mutates must be an array",
            )
            effect_rows: list[tuple[str, str, str]] = []
            for effect_index, effect in enumerate(effects):
                label = f"{event_label}.common_case_effects[{effect_index}]"
                action = effect["action"]
                cardinality = effect["cardinality"]
                resource = effect["resource"]
                require(
                    action in {"CONDITIONAL_COMPARE", "RESERVE", "WRITE"},
                    f"{label}: unknown resource action",
                )
                require(
                    isinstance(cardinality, str)
                    and SEMANTIC_ID.fullmatch(cardinality) is not None,
                    f"{label}: invalid resource cardinality",
                )
                require(
                    isinstance(resource, str)
                    and SEMANTIC_RESOURCE_REF.fullmatch(resource) is not None,
                    f"{label}: invalid semantic resource identity",
                )
                if resource.startswith("EXTERNAL."):
                    require(
                        action == "CONDITIONAL_COMPARE"
                        and resource in EXTERNAL_COMPARE_RESOURCES,
                        (f"{label}: external resources are a closed compare-only set"),
                    )
                else:
                    require(
                        resource in registry,
                        f"{label}: local resource has no owner declaration",
                    )
                    if action in {"RESERVE", "WRITE"}:
                        require_exact(
                            registry[resource],
                            selector["selector_id"],
                            f"{label}: mutating effect owner",
                        )
                effect_rows.append((action, cardinality, resource))
            require_unique(effect_rows, f"{event_label}: common resource effects")

            require(
                all(
                    isinstance(resource, str)
                    and SEMANTIC_RESOURCE_REF.fullmatch(resource) is not None
                    and not resource.startswith("EXTERNAL.")
                    and resource in registry
                    for resource in mutations
                ),
                (
                    f"{event_label}: common-case mutations contain an "
                    "unowned or external resource"
                ),
            )
            require_unique(mutations, f"{event_label}: common-case mutations")
            require_exact(
                set(mutations),
                {
                    effect["resource"]
                    for effect in effects
                    if effect["action"] in {"RESERVE", "WRITE"}
                },
                f"{event_label}: mutation/effect resource bijection",
            )


def _run_owned_resource_registry_self_test() -> int:
    baseline = {
        "selectors": [
            {
                "events": [
                    {
                        "common_case_effects": [
                            {
                                "action": "WRITE",
                                "cardinality": "EXACT_ONE_KEY",
                                "resource": "SAMPLE.HEAD",
                            },
                            {
                                "action": "CONDITIONAL_COMPARE",
                                "cardinality": "EXACTLY_ONE",
                                "resource": "SECURITY.SELECTOR",
                            },
                        ],
                        "common_case_mutates": ["SAMPLE.HEAD"],
                    }
                ],
                "owned_resources": [
                    {
                        "owner_selector_id": "SAMPLE",
                        "resource": "SAMPLE.HEAD",
                    },
                    {
                        "owner_selector_id": "SAMPLE",
                        "resource": "SAMPLE.STATE_DOMAIN.ROOT",
                    },
                ],
                "selector_id": "SAMPLE",
                "state_domains": [{"state_domain": "ROOT"}],
            },
            {
                "events": [],
                "owned_resources": [
                    {
                        "owner_selector_id": "SECURITY",
                        "resource": "SECURITY.SELECTOR",
                    },
                    {
                        "owner_selector_id": "SECURITY",
                        "resource": "SECURITY.STATE_DOMAIN.ROOT",
                    },
                ],
                "selector_id": "SECURITY",
                "state_domains": [{"state_domain": "ROOT"}],
            },
        ]
    }
    _validate_owned_resource_registry(baseline)
    mutants: list[tuple[str, Any]] = [
        (
            "wrong resource owner",
            lambda value: value["selectors"][0]["owned_resources"][0].__setitem__(
                "owner_selector_id", "OTHER"
            ),
        ),
        (
            "unsorted resource registry",
            lambda value: value["selectors"][0]["owned_resources"].reverse(),
        ),
        (
            "duplicate resource declaration",
            lambda value: value["selectors"][0]["owned_resources"].append(
                copy.deepcopy(value["selectors"][0]["owned_resources"][0])
            ),
        ),
        (
            "missing state-domain resource",
            lambda value: value["selectors"][0]["owned_resources"].pop(),
        ),
        (
            "unowned local effect",
            lambda value: value["selectors"][0]["events"][0]["common_case_effects"][
                0
            ].__setitem__("resource", "SAMPLE.MISSING"),
        ),
        (
            "unknown external alias",
            lambda value: value["selectors"][0]["events"][0]["common_case_effects"][
                1
            ].__setitem__("resource", "EXTERNAL.UNKNOWN"),
        ),
        (
            "cross-owner write",
            lambda value: value["selectors"][0]["events"][0]["common_case_effects"][
                1
            ].__setitem__("action", "WRITE"),
        ),
        (
            "cross-owner mutation",
            lambda value: value["selectors"][0]["events"][0][
                "common_case_mutates"
            ].append("SECURITY.SELECTOR"),
        ),
        (
            "duplicate effect",
            lambda value: value["selectors"][0]["events"][0][
                "common_case_effects"
            ].append(
                copy.deepcopy(
                    value["selectors"][0]["events"][0]["common_case_effects"][0]
                )
            ),
        ),
        (
            "duplicate mutation",
            lambda value: value["selectors"][0]["events"][0][
                "common_case_mutates"
            ].append("SAMPLE.HEAD"),
        ),
    ]
    for label, mutate in mutants:
        hostile = copy.deepcopy(baseline)
        mutate(hostile)
        try:
            _validate_owned_resource_registry(hostile)
        except ClosureCheckError:
            pass
        else:
            fail(f"owned resource registry self-test accepted {label}")
    return len(mutants)


def _is_semantic_identifier_token(token: str) -> bool:
    return (
        "_" in token
        or token.isupper()
        or any(character.isupper() for character in token[1:])
    )


def _open_questions_section(
    text: str,
    *,
    label: str,
) -> str:
    """Return the one exact ADR Open-questions section."""

    headings = list(OPEN_QUESTIONS_HEADING_RE.finditer(text))
    require_exact(
        len(headings),
        1,
        f"{label}: exact {OPEN_QUESTIONS_HEADING!r} heading count",
    )
    section_start = headings[0].end()
    next_heading = NEXT_LEVEL_TWO_HEADING_RE.search(text, section_start)
    section_end = next_heading.start() if next_heading is not None else len(text)
    return text[section_start:section_end]


def _extract_open_question_identifiers(
    text: str,
    *,
    label: str,
) -> tuple[str, ...]:
    """Extract legacy exact-name literals so externalization can reject them."""

    section = _open_questions_section(text, label=label)
    identifiers = {
        token
        for code_span in (
            BACKTICK_CODE_RE.findall(section) + HTML_CODE_RE.findall(section)
        )
        for token in IDENTIFIER_TOKEN_RE.findall(code_span)
        if _is_semantic_identifier_token(token)
    }
    return tuple(sorted(identifiers))


def _extract_allocation_anchor(
    text: str,
    *,
    expected_anchor_id: str,
    label: str,
) -> str:
    """Require one stable anchor and no legacy literal allocation inventory."""

    section = _open_questions_section(text, label=label)
    section_anchors = ALLOCATION_ANCHOR_RE.findall(section)
    require_exact(
        section_anchors,
        [expected_anchor_id],
        f"{label}: stable external-allocation anchor",
    )
    require_exact(
        ALLOCATION_ANCHOR_RE.findall(text),
        [expected_anchor_id],
        f"{label}: document-wide external-allocation anchor",
    )
    legacy_identifiers = _extract_open_question_identifiers(text, label=label)
    require(
        not legacy_identifiers,
        (
            f"{label}: Open questions retains literal allocation identifiers "
            f"instead of the external inventory: {list(legacy_identifiers)[:3]}"
        ),
    )
    plain_semantic_identifiers = sorted(
        {
            token
            for token in IDENTIFIER_TOKEN_RE.findall(section)
            if _is_semantic_identifier_token(token)
            and token not in ALLOWED_EXTERNAL_ANCHOR_SECTION_TOKENS
        }
    )
    require(
        not plain_semantic_identifiers,
        (
            f"{label}: Open questions retains semantic identifier literals "
            f"outside the external inventory: {plain_semantic_identifiers[:3]}"
        ),
    )
    return expected_anchor_id


def _accepted_allocation_prose_identifiers(text: str) -> set[str]:
    """Return identifiers only from sections that state accepted semantics."""

    headings = list(re.finditer(r"(?m)^## ([^\r\n]+?)[ \t]*\r?$", text))
    identifiers: set[str] = set()
    for index, heading in enumerate(headings):
        if heading.group(1) not in ACCEPTED_ALLOCATION_PROSE_HEADINGS:
            continue
        section_end = (
            headings[index + 1].start() if index + 1 < len(headings) else len(text)
        )
        identifiers.update(
            IDENTIFIER_TOKEN_RE.findall(text[heading.end() : section_end])
        )
    return identifiers


def _run_adr_extraction_self_test() -> int:
    anchor_id = ADR_ALLOCATION_ANCHOR_IDS[0]
    text = f"""# Synthetic ADR

`BEFORE_SECTION`

## Open questions

<a id="{anchor_id}"></a>

The external inventory contains the exhaustive allocation rows.

## Consequences

`AFTER_SECTION`
"""
    require_exact(
        _extract_allocation_anchor(
            text,
            expected_anchor_id=anchor_id,
            label="synthetic ADR",
        ),
        anchor_id,
        "Open-questions anchor boundary",
    )
    semantic_sections = """# Synthetic ADR

## Proposed decision

`AcceptedType`

## Rejected alternatives

`RejectedType`

## Invalid or hostile example

`HostileType`
"""
    require_exact(
        _accepted_allocation_prose_identifiers(semantic_sections),
        {"AcceptedType"},
        "accepted allocation prose boundary",
    )
    hostile_cases = (
        (text.replace("## Open questions", "## Questions"), "missing heading"),
        (
            text.replace(
                "## Consequences",
                "## Open questions\n\n## Consequences",
            ),
            "duplicate heading",
        ),
        (text.replace(f'<a id="{anchor_id}"></a>\n', ""), "deleted anchor"),
        (
            text.replace(
                f'<a id="{anchor_id}"></a>',
                (f'<a id="{anchor_id}"></a>\n<a id="{anchor_id}"></a>'),
            ),
            "duplicated anchor",
        ),
        (
            text.replace(
                anchor_id,
                ADR_ALLOCATION_ANCHOR_IDS[1],
            ),
            "reassigned anchor",
        ),
        (
            text.replace(
                "The external inventory contains",
                "`RestoredLiteralType`\n\nThe external inventory contains",
            ),
            "legacy literal allocation inventory",
        ),
        (
            text.replace(
                "The external inventory contains",
                "``RESTORED_DOUBLE_LITERAL``\n\nThe external inventory contains",
            ),
            "legacy double-backtick allocation inventory",
        ),
        (
            text.replace(
                "The external inventory contains",
                (
                    "```text\nRESTORED_FENCED_LITERAL\n```\n\n"
                    "The external inventory contains"
                ),
            ),
            "legacy fenced allocation inventory",
        ),
        (
            text.replace(
                "The external inventory contains",
                "<code>RestoredHtmlLiteral</code>\n\nThe external inventory contains",
            ),
            "legacy HTML-code allocation inventory",
        ),
        (
            text.replace(
                "The external inventory contains",
                "RestoredPlainLiteral\n\nThe external inventory contains",
            ),
            "legacy plain-text allocation inventory",
        ),
        (
            text.replace(
                "## Consequences",
                (f'## Consequences\n\n<a id="{anchor_id}"></a>'),
            ),
            "duplicate anchor outside Open questions",
        ),
    )
    for hostile, label in hostile_cases:
        try:
            _extract_allocation_anchor(
                hostile,
                expected_anchor_id=anchor_id,
                label=label,
            )
        except ClosureCheckError:
            pass
        else:
            fail(f"ADR extraction self-test accepted {label}")
    return 2 + len(hostile_cases)


def _iter_string_values(value: Any) -> list[str]:
    strings: list[str] = []
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, str):
            strings.append(current)
        elif isinstance(current, list):
            pending.extend(current)
        elif isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())
    return strings


def _semantic_artifact_references(data: dict[str, Any]) -> set[str]:
    excluded_top_level_keys = {
        "adr_allocation_oracle",
        "artifacts",
        "closure_commitments",
    }
    references = {
        value
        for key, item in data.items()
        if key not in excluded_top_level_keys
        for value in _iter_string_values(item)
        if ALLOCATION_REF.fullmatch(value) is not None
    }
    declared_resources = {
        declaration.get("resource")
        for selector in data.get("selectors", [])
        if isinstance(selector, dict)
        for declaration in selector.get("owned_resources", [])
        if isinstance(declaration, dict)
    }
    references.update(
        backing
        for resource, backing in SUBORDINATE_HEAD_BACKINGS.items()
        if resource in declared_resources
    )
    return references


def _validate_artifact_registry_usage(
    data: dict[str, Any],
    artifacts: set[str],
    *,
    allow_known_incomplete: bool = False,
) -> None:
    """Require the registry to equal the model's semantic artifact references."""

    referenced = _semantic_artifact_references(data)
    unregistered = referenced - artifacts
    if not allow_known_incomplete:
        require(
            not unregistered,
            (
                "semantic model references artifacts absent from the registry: "
                f"count={len(unregistered)} sample={sorted(unregistered)[:3]}"
            ),
        )
    unused = artifacts - referenced
    require(
        not unused,
        (
            "artifact registry contains entries with no semantic model use: "
            f"count={len(unused)} sample={sorted(unused)[:3]}"
        ),
    )


def _run_artifact_registry_usage_self_test() -> int:
    used = "used-type::UsedType"
    unregistered = "unregistered-type::UnregisteredType"
    synthetic = {
        "adr_allocation_oracle": {
            "model_ref": "oracle-only-type::OracleOnlyType",
        },
        "artifacts": [used],
        "closure_commitments": {
            "artifact": "commitment-only-type::CommitmentOnlyType",
        },
        "profile": {"artifact": used},
    }
    _validate_artifact_registry_usage(synthetic, {used})
    subordinate_resource = "GALADRIEL_LIFECYCLE.GALADRIEL_ASSESSMENT_HANDOFF_STATE_HEAD"
    subordinate_backing = SUBORDINATE_HEAD_BACKINGS[subordinate_resource]
    resource_backed = {
        **synthetic,
        "selectors": [
            {
                "owned_resources": [
                    {
                        "owner_selector_id": "GALADRIEL_LIFECYCLE",
                        "resource": subordinate_resource,
                    }
                ]
            }
        ],
    }
    _validate_artifact_registry_usage(
        resource_backed,
        {used, subordinate_backing},
    )
    for hostile, registry, label in (
        (
            {**synthetic, "profile": {"artifact": unregistered}},
            {used},
            "unregistered semantic reference",
        ),
        (
            synthetic,
            {used, "unused-type::UnusedType"},
            "unused registry entry",
        ),
        (
            resource_backed,
            {used},
            "unregistered subordinate resource backing",
        ),
    ):
        try:
            _validate_artifact_registry_usage(hostile, registry)
        except ClosureCheckError:
            pass
        else:
            fail(f"artifact registry self-test accepted {label}")
    return 5


def _structural_profile_allocations(
    data: dict[str, Any],
    *,
    accumulator: _AllocationAccumulator | None = None,
) -> set[ModelAllocation]:
    """Return owner-free structural profile units with aggregated provenance."""

    target = accumulator if accumulator is not None else _AllocationAccumulator()
    named_profile_paths: dict[str, str] = {}
    named_profile_semantic_refs: dict[str, str] = {}
    structural_references: set[str] = set()

    def escape_pointer_token(value: str) -> str:
        return value.replace("~", "~0").replace("/", "~1")

    def add_named_profile(
        profile_id: str,
        pointer: str,
        *,
        label: str,
        semantic_id_required: bool = True,
    ) -> None:
        identifier_pattern = (
            SEMANTIC_ID if semantic_id_required else IDENTIFIER_TOKEN_RE
        )
        require(
            identifier_pattern.fullmatch(profile_id) is not None,
            f"{label}: invalid named structural profile ID",
        )
        prior = named_profile_paths.get(profile_id)
        require(
            prior is None or prior == pointer,
            (
                f"{label}: named structural profile {profile_id} is defined "
                f"at both {prior} and {pointer}"
            ),
        )
        named_profile_paths[profile_id] = pointer
        semantic_ref = f"profile-id::{profile_id}"
        named_profile_semantic_refs[profile_id] = semantic_ref
        target.add(
            "PROFILE",
            profile_id,
            semantic_ref,
            origin=AllocationEvidence(
                "STRUCTURAL_PROFILE_DEFINITION",
                f"json-pointer::{pointer}",
            ),
        )

    def walk_named_profiles(value: Any, pointer: str, *, label: str) -> None:
        if isinstance(value, dict):
            if "profile_id" in value:
                profile_id = value["profile_id"]
                require(
                    isinstance(profile_id, str),
                    f"{label}.profile_id: expected a string",
                )
                add_named_profile(profile_id, pointer, label=label)
            for child_key, child in value.items():
                walk_named_profiles(
                    child,
                    f"{pointer}/{escape_pointer_token(child_key)}",
                    label=f"{label}.{child_key}",
                )
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk_named_profiles(
                    child,
                    f"{pointer}/{index}",
                    label=f"{label}[{index}]",
                )

    def walk_structural_references(value: Any, *, label: str) -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                if child_key == "profile_ref" or child_key.endswith(
                    ("_profile_ref", "_table_ref")
                ):
                    require(
                        isinstance(child, str),
                        f"{label}.{child_key}: structural reference must be a string",
                    )
                    structural_references.add(child)
                walk_structural_references(
                    child,
                    label=f"{label}.{child_key}",
                )
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk_structural_references(
                    child,
                    label=f"{label}[{index}]",
                )

    for key, value in data.items():
        if not (
            key.endswith("_profile")
            or key.endswith("_profiles")
            or key.endswith("_profile_catalog")
        ):
            continue
        require(
            isinstance(value, dict),
            f"{key}: structural profile must be an object",
        )
        require(
            re.fullmatch(r"[a-z][a-z0-9_]*", key) is not None,
            f"{key}: invalid structural profile identifier",
        )
        escaped_key = escape_pointer_token(key)
        root_pointer = f"/{escaped_key}"
        target.add(
            "PROFILE",
            key,
            root_pointer,
            origin=AllocationEvidence(
                "STRUCTURAL_PROFILE_DEFINITION",
                f"json-pointer::{root_pointer}",
            ),
        )
        if key.endswith("_profiles"):
            for profile_id, profile in value.items():
                if SEMANTIC_ID.fullmatch(profile_id) is None:
                    continue
                require(
                    isinstance(profile, dict),
                    (f"{key}.{profile_id}: named structural profile must be an object"),
                )
                add_named_profile(
                    profile_id,
                    f"{root_pointer}/{escape_pointer_token(profile_id)}",
                    label=f"{key}.{profile_id}",
                )
        walk_named_profiles(value, root_pointer, label=key)

    walk_structural_references(data, label="$")
    allocations = target.build()
    allocated_profile_names = {row.exact_name for row in allocations}
    for reference in sorted(structural_references):
        if reference in allocated_profile_names:
            matching = [
                allocation
                for allocation in allocations
                if allocation.kind == "PROFILE" and allocation.exact_name == reference
            ]
            require(
                len(matching) == 1,
                (
                    "structural profile reference is ambiguous across semantic "
                    f"units: {reference}"
                ),
            )
            target.add(
                matching[0].kind,
                matching[0].exact_name,
                matching[0].semantic_ref,
                signal=AllocationEvidence(
                    "STRUCTURAL_PROFILE_REFERENCE",
                    f"profile-reference::{reference}",
                ),
            )
            continue
        lowered = reference.lower()
        if lowered in data and (
            lowered.endswith("_profile")
            or lowered.endswith("_profiles")
            or lowered.endswith("_profile_catalog")
        ):
            require(
                isinstance(data[lowered], dict),
                f"{reference}: referenced structural profile must be an object",
            )
            add_named_profile(
                reference,
                f"/{escape_pointer_token(lowered)}",
                label=f"structural reference {reference}",
            )
            allocated_profile_names.add(reference)
            target.add(
                "PROFILE",
                reference,
                named_profile_semantic_refs[reference],
                signal=AllocationEvidence(
                    "STRUCTURAL_PROFILE_REFERENCE",
                    f"profile-reference::{reference}",
                ),
            )
            continue
        if "." in reference:
            profile_target: Any = data
            pointer_tokens: list[str] = []
            for token in reference.split("."):
                require(
                    isinstance(profile_target, dict) and token in profile_target,
                    f"{reference}: structural reference target is absent",
                )
                profile_target = profile_target[token]
                pointer_tokens.append(escape_pointer_token(token))
            require(
                isinstance(profile_target, dict),
                f"{reference}: structural reference target must be an object",
            )
            exact_name = reference.rsplit(".", 1)[1]
            semantic_ref = f"profile-ref::{reference}"
            pointer = "/" + "/".join(pointer_tokens)
            target.add(
                "PROFILE",
                exact_name,
                semantic_ref,
                origin=AllocationEvidence(
                    "STRUCTURAL_PROFILE_DEFINITION",
                    f"json-pointer::{pointer}",
                ),
                signal=AllocationEvidence(
                    "STRUCTURAL_PROFILE_REFERENCE",
                    f"profile-reference::{reference}",
                ),
            )
            allocated_profile_names.add(exact_name)
            continue
        fail(f"{reference}: structural reference has no allocated definition")
    allocations = target.build()
    require(
        bool(allocations),
        "expanded model has no top-level structural profiles",
    )
    return allocations


def _run_structural_profile_allocation_self_test() -> int:
    baseline = {
        "actor_profiles": {},
        "decision_relation_profile": {},
        "references": {
            "consumer_table_ref": "sample_profile.nested",
            "profile_ref": "DECISION_RELATION_PROFILE",
        },
        "sample_profile": {"nested": {}},
        "sample_profiles": {
            "NAMED_PROFILE": {},
            "metadata": {},
        },
        "sample_profile_catalog": {
            "guards": [
                {
                    "profile_id": "CATALOG_PROFILE",
                    "value": {},
                }
            ]
        },
        "unrelated": {},
    }
    expected = {
        ModelAllocation("PROFILE", "actor_profiles", "/actor_profiles"),
        ModelAllocation(
            "PROFILE",
            "DECISION_RELATION_PROFILE",
            "profile-id::DECISION_RELATION_PROFILE",
        ),
        ModelAllocation(
            "PROFILE",
            "decision_relation_profile",
            "/decision_relation_profile",
        ),
        ModelAllocation(
            "PROFILE",
            "nested",
            "profile-ref::sample_profile.nested",
        ),
        ModelAllocation("PROFILE", "sample_profile", "/sample_profile"),
        ModelAllocation(
            "PROFILE",
            "sample_profile_catalog",
            "/sample_profile_catalog",
        ),
        ModelAllocation(
            "PROFILE",
            "CATALOG_PROFILE",
            "profile-id::CATALOG_PROFILE",
        ),
        ModelAllocation("PROFILE", "sample_profiles", "/sample_profiles"),
        ModelAllocation(
            "PROFILE",
            "NAMED_PROFILE",
            "profile-id::NAMED_PROFILE",
        ),
    }
    require_exact(
        _structural_profile_allocations(baseline),
        expected,
        "structural PROFILE allocation surface",
    )
    added = copy.deepcopy(baseline)
    added["new_profile"] = {}
    require(
        _structural_profile_allocations(added)
        == expected | {ModelAllocation("PROFILE", "new_profile", "/new_profile")},
        "structural PROFILE allocation missed an added profile",
    )
    ordered_catalog = copy.deepcopy(baseline)
    ordered_catalog["sample_profile_catalog"]["guards"].append(
        {"profile_id": "SECOND_CATALOG_PROFILE", "value": {}}
    )
    reordered_catalog = copy.deepcopy(ordered_catalog)
    reordered_catalog["sample_profile_catalog"]["guards"].reverse()
    ordered_model = _structural_profile_allocations(ordered_catalog)
    reordered_model = _structural_profile_allocations(reordered_catalog)
    require_exact(
        _model_allocation_sha256(ordered_model),
        _model_allocation_sha256(reordered_model),
        "named profile array-order-independent semantic identity",
    )
    require(
        _model_origin_signal_commitment(ordered_model)
        != _model_origin_signal_commitment(reordered_model),
        "named profile origin movement was not visible in its separate commitment",
    )
    hostile = copy.deepcopy(baseline)
    hostile["sample_profile"] = []
    try:
        _structural_profile_allocations(hostile)
    except ClosureCheckError:
        pass
    else:
        fail("structural PROFILE allocation accepted a non-object profile")
    hostile_nested = copy.deepcopy(baseline)
    hostile_nested["sample_profiles"]["NAMED_PROFILE"] = []
    try:
        _structural_profile_allocations(hostile_nested)
    except ClosureCheckError:
        pass
    else:
        fail("structural PROFILE allocation accepted a non-object named profile")
    duplicate_named = copy.deepcopy(baseline)
    duplicate_named["sample_profile_catalog"]["guards"].append(
        {
            "profile_id": "CATALOG_PROFILE",
            "value": {},
        }
    )
    try:
        _structural_profile_allocations(duplicate_named)
    except ClosureCheckError:
        pass
    else:
        fail("structural PROFILE allocation accepted a duplicate named profile")
    hostile_catalog_id = copy.deepcopy(baseline)
    hostile_catalog_id["sample_profile_catalog"]["guards"][0]["profile_id"] = (
        "not-a-semantic-id"
    )
    try:
        _structural_profile_allocations(hostile_catalog_id)
    except ClosureCheckError:
        pass
    else:
        fail("structural PROFILE allocation accepted an invalid catalog profile ID")
    dangling_reference = copy.deepcopy(baseline)
    dangling_reference["references"]["profile_ref"] = "MISSING_PROFILE"
    try:
        _structural_profile_allocations(dangling_reference)
    except ClosureCheckError:
        pass
    else:
        fail("structural PROFILE allocation accepted a dangling structural reference")
    return 9


def _model_allocations(data: dict[str, Any]) -> set[ModelAllocation]:
    """Return one owner-free unit per stable kind/name/semantic-ref triple."""

    selectors = data["selectors"]
    require(isinstance(selectors, list), "selectors must be an array")
    accumulator = _AllocationAccumulator()
    _structural_profile_allocations(data, accumulator=accumulator)
    selector_references: dict[str, set[str]] = {}
    resource_backings: dict[str, set[str]] = {}
    event_transition_references: set[str] = set()
    selector_ids: set[str] = set()
    resource_identities: set[str] = set()

    for selector_index, selector in enumerate(selectors):
        label = f"selectors[{selector_index}]"
        require(isinstance(selector, dict), f"{label}: expected an object")
        selector_id = selector.get("selector_id")
        require(
            isinstance(selector_id, str)
            and SEMANTIC_ID.fullmatch(selector_id) is not None,
            f"{label}: invalid selector ID",
        )
        require(selector_id not in selector_ids, f"{label}: duplicate selector ID")
        selector_ids.add(selector_id)
        selector_references[selector_id] = set(_iter_string_values(selector))
        selector_ref = f"selector-id::{selector_id}"
        accumulator.add(
            "SELECTOR",
            selector_id,
            selector_ref,
            origin=AllocationEvidence("SELECTOR_DECLARATION", selector_ref),
        )

        owned_resources = selector.get("owned_resources")
        require(
            isinstance(owned_resources, list),
            f"{label}.owned_resources must be an array",
        )
        for resource_index, declaration in enumerate(owned_resources):
            declaration_label = f"{label}.owned_resources[{resource_index}]"
            require(
                isinstance(declaration, dict)
                and set(declaration) == OWNED_RESOURCE_KEYS,
                f"{declaration_label}: expected an exact owned-resource declaration",
            )
            declared_selector = declaration["owner_selector_id"]
            resource = declaration["resource"]
            require_exact(
                declared_selector,
                selector_id,
                f"{declaration_label}: declaration selector",
            )
            require(
                isinstance(resource, str)
                and RESOURCE_EXACT_NAME.fullmatch(resource) is not None
                and resource.startswith(f"{selector_id}."),
                f"{declaration_label}: invalid owned resource identity",
            )
            require(
                resource not in resource_identities,
                f"{declaration_label}: duplicate owned resource identity",
            )
            resource_identities.add(resource)
            resource_ref = f"resource-id::{resource}"
            accumulator.add(
                "RESOURCE",
                resource,
                resource_ref,
                origin=AllocationEvidence(
                    "RESOURCE_DECLARATION",
                    f"{selector_ref}/{resource_ref}",
                ),
            )
            backing = SUBORDINATE_HEAD_BACKINGS.get(resource)
            if backing is not None:
                resource_backings.setdefault(backing, set()).add(resource_ref)

        state_domains = selector.get("state_domains")
        events = selector.get("events")
        require(
            isinstance(state_domains, list),
            f"{label}.state_domains must be an array",
        )
        require(isinstance(events, list), f"{label}.events must be an array")
        for domain_index, domain in enumerate(state_domains):
            domain_label = f"{label}.state_domains[{domain_index}]"
            require(isinstance(domain, dict), f"{domain_label}: expected an object")
            domain_id = domain.get("state_domain")
            states = domain.get("states")
            require(
                isinstance(domain_id, str)
                and SEMANTIC_ID.fullmatch(domain_id) is not None,
                f"{domain_label}: invalid state domain",
            )
            require(isinstance(states, list), f"{domain_label}.states must be an array")
            for state_index, state in enumerate(states):
                require(
                    isinstance(state, str) and SEMANTIC_ID.fullmatch(state) is not None,
                    f"{domain_label}.states[{state_index}]: invalid state",
                )
                state_ref = f"state-id::{selector_id}.{domain_id}.{state}"
                accumulator.add(
                    "STATE",
                    state,
                    state_ref,
                    origin=AllocationEvidence(
                        "STATE_DECLARATION",
                        f"{selector_ref}/state-domain::{domain_id}/state::{state}",
                    ),
                )

        for event_index, event in enumerate(events):
            event_label = f"{label}.events[{event_index}]"
            require(isinstance(event, dict), f"{event_label}: expected an object")
            event_id = event.get("event_id")
            transition_kind = event.get("transition_kind")
            require(
                isinstance(event_id, str)
                and SEMANTIC_ID.fullmatch(event_id) is not None,
                f"{event_label}: invalid event ID",
            )
            require(
                isinstance(transition_kind, str)
                and ALLOCATION_REF.fullmatch(transition_kind) is not None,
                f"{event_label}: invalid transition kind",
            )
            event_transition_references.add(transition_kind)
            event_location = f"{selector_ref}/event-id::{event_id}"
            accumulator.add(
                "EVENT",
                event_id,
                transition_kind,
                origin=AllocationEvidence("DECLARED_EVENT", event_location),
            )
            subordinate_transition_kinds = event.get(
                "subordinate_transition_kinds",
                [],
            )
            require(
                isinstance(subordinate_transition_kinds, list),
                (f"{event_label}.subordinate_transition_kinds must be an array"),
            )
            for subordinate_index, subordinate_ref in enumerate(
                subordinate_transition_kinds
            ):
                require(
                    isinstance(subordinate_ref, str)
                    and ALLOCATION_REF.fullmatch(subordinate_ref) is not None,
                    (
                        f"{event_label}.subordinate_transition_kinds"
                        f"[{subordinate_index}]: invalid transition kind"
                    ),
                )
                event_transition_references.add(subordinate_ref)
                _slug, subordinate_name = subordinate_ref.split("::", 1)
                accumulator.add(
                    "EVENT",
                    subordinate_name,
                    subordinate_ref,
                    origin=AllocationEvidence(
                        "SUBORDINATE_EVENT_DECLARATION",
                        f"{event_location}/subordinate-event::{subordinate_ref}",
                    ),
                )

    artifacts = data["artifacts"]
    require(isinstance(artifacts, list), "artifacts must be an array")
    for index, reference in enumerate(artifacts):
        require(
            isinstance(reference, str)
            and ALLOCATION_REF.fullmatch(reference) is not None,
            f"artifacts[{index}]: invalid allocation reference",
        )
        _slug, exact_name = reference.split("::", 1)
        kind = "EVENT" if reference in event_transition_references else "TYPE"
        accumulator.add(
            kind,
            exact_name,
            reference,
            origin=AllocationEvidence(
                "ARTIFACT_REGISTRY_ENTRY",
                f"artifact-ref::{reference}",
            ),
        )
        for selector_id, references in sorted(selector_references.items()):
            if reference in references:
                accumulator.add(
                    kind,
                    exact_name,
                    reference,
                    signal=AllocationEvidence(
                        "SELECTOR_USAGE",
                        f"selector-id::{selector_id}",
                    ),
                )
        for resource_ref in sorted(resource_backings.get(reference, set())):
            accumulator.add(
                kind,
                exact_name,
                reference,
                signal=AllocationEvidence("RESOURCE_BACKING", resource_ref),
            )
    return accumulator.build()


def _model_allocation_sha256(model: set[ModelAllocation]) -> str:
    return model_allocation_projection_sha256(
        [allocation.identity_row() for allocation in model]
    )


def _model_origin_signal_commitment(
    model: set[ModelAllocation],
) -> tuple[int, str]:
    """Bind evidence drift separately without changing any semantic unit ID."""

    return model_origin_signal_projection_commitment(
        [allocation.evidence_row() for allocation in model]
    )


def _run_artifact_allocation_identity_self_test() -> int:
    baseline = {
        "artifacts": ["sample-type::SampleType"],
        "sample_profile": {},
        "selectors": [],
    }
    baseline_unit = ModelAllocation(
        "TYPE",
        "SampleType",
        "sample-type::SampleType",
    )
    require(
        baseline_unit in _model_allocations(baseline),
        "artifact allocation identity self-test lost its baseline type",
    )

    aliased = copy.deepcopy(baseline)
    aliased["artifacts"].append("other-sample-type::SampleType")
    same_name_units = {
        allocation
        for allocation in _model_allocations(aliased)
        if allocation.kind == "TYPE" and allocation.exact_name == "SampleType"
    }
    require_exact(
        len(same_name_units),
        2,
        "artifact allocation identity distinct semantic references",
    )
    require_exact(
        len({allocation.unit_id for allocation in same_name_units}),
        2,
        "artifact allocation identity domain-separated unit IDs",
    )

    distinct_transition_domains = {
        "artifacts": [
            "first-transition-kind::SAME_EVENT",
            "second-event-kind::SAME_EVENT",
            "subordinate-transition-kind::SUBORDINATE_EVENT",
        ],
        "sample_profile": {},
        "selectors": [
            {
                "events": [
                    {
                        "event_id": "SAME_EVENT",
                        "subordinate_transition_kinds": [
                            "subordinate-transition-kind::SUBORDINATE_EVENT"
                        ],
                        "transition_kind": "first-transition-kind::SAME_EVENT",
                    },
                    {
                        "event_id": "SAME_EVENT",
                        "transition_kind": "second-event-kind::SAME_EVENT",
                    },
                ],
                "owned_resources": [],
                "selector_id": "SAMPLE_SELECTOR",
                "state_domains": [],
            }
        ],
    }
    transition_rows = {
        row
        for row in _model_allocations(distinct_transition_domains)
        if row.kind == "EVENT"
    }
    require(
        transition_rows
        == {
            ModelAllocation(
                "EVENT",
                "SAME_EVENT",
                "first-transition-kind::SAME_EVENT",
            ),
            ModelAllocation(
                "EVENT",
                "SAME_EVENT",
                "second-event-kind::SAME_EVENT",
            ),
            ModelAllocation(
                "EVENT",
                "SUBORDINATE_EVENT",
                "subordinate-transition-kind::SUBORDINATE_EVENT",
            ),
        },
        "artifact allocation identity collapsed distinct transition domains",
    )
    require(
        not {
            row
            for row in _model_allocations(distinct_transition_domains)
            if row.kind == "TYPE" and row.exact_name == "SAME_EVENT"
        },
        "artifact allocation identity double-counted an event-kind as TYPE",
    )
    misleading_slug = copy.deepcopy(baseline)
    misleading_slug["artifacts"] = ["orphan-transition-kind::NotAnEvent"]
    require(
        (
            ModelAllocation(
                "TYPE",
                "NotAnEvent",
                "orphan-transition-kind::NotAnEvent",
            )
        )
        in _model_allocations(misleading_slug),
        "artifact allocation identity inferred EVENT authority from a slug",
    )
    subordinate_resource = "GALADRIEL_LIFECYCLE.GALADRIEL_ASSESSMENT_HANDOFF_STATE_HEAD"
    subordinate_backing = SUBORDINATE_HEAD_BACKINGS[subordinate_resource]
    resource_owned_artifact = {
        "actor_profiles": {},
        "artifacts": [subordinate_backing],
        "selectors": [
            {
                "events": [],
                "owned_resources": [
                    {
                        "owner_selector_id": "GALADRIEL_LIFECYCLE",
                        "resource": subordinate_resource,
                    }
                ],
                "selector_id": "GALADRIEL_LIFECYCLE",
                "state_domains": [],
            }
        ],
    }
    backing_unit = next(
        allocation
        for allocation in _model_allocations(resource_owned_artifact)
        if allocation.kind == "TYPE" and allocation.semantic_ref == subordinate_backing
    )
    require(
        AllocationEvidence(
            "RESOURCE_BACKING",
            f"resource-id::{subordinate_resource}",
        )
        in backing_unit.signals,
        "resource backing was not retained as non-authoritative evidence",
    )
    resource_backing_removed = copy.deepcopy(resource_owned_artifact)
    resource_backing_removed["selectors"][0]["owned_resources"].clear()
    unbacked_unit = next(
        allocation
        for allocation in _model_allocations(resource_backing_removed)
        if allocation.kind == "TYPE" and allocation.semantic_ref == subordinate_backing
    )
    require_exact(
        backing_unit.unit_id,
        unbacked_unit.unit_id,
        "resource-backing-independent unit ID",
    )
    require(
        model_origin_signal_projection_commitment([backing_unit.evidence_row()])
        != model_origin_signal_projection_commitment([unbacked_unit.evidence_row()]),
        "resource backing change did not alter the separate signal commitment",
    )

    overlap_unit = next(
        allocation
        for allocation in _model_allocations(distinct_transition_domains)
        if allocation.kind == "EVENT"
        and allocation.semantic_ref == "first-transition-kind::SAME_EVENT"
    )
    require_exact(
        {origin.evidence_kind for origin in overlap_unit.origins},
        {"ARTIFACT_REGISTRY_ENTRY", "DECLARED_EVENT"},
        "artifact/declared-event origin aggregation",
    )

    shared_reference = "shared-type::SharedType"
    selector_template = {
        "events": [],
        "owned_resources": [],
        "state_domains": [],
        "usage": None,
    }
    first_usage = {
        "actor_profiles": {},
        "artifacts": [shared_reference],
        "selectors": [
            {
                **copy.deepcopy(selector_template),
                "selector_id": "CONSUMER_A",
                "usage": shared_reference,
            },
            {**copy.deepcopy(selector_template), "selector_id": "CONSUMER_B"},
        ],
    }
    second_usage = copy.deepcopy(first_usage)
    second_usage["selectors"][0]["usage"] = None
    second_usage["selectors"][1]["usage"] = shared_reference
    first_model = _model_allocations(first_usage)
    second_model = _model_allocations(second_usage)
    require_exact(
        _model_allocation_sha256(first_model),
        _model_allocation_sha256(second_model),
        "consumer-usage-independent mechanical allocation identity",
    )
    require(
        _model_origin_signal_commitment(first_model)
        != _model_origin_signal_commitment(second_model),
        "consumer usage change did not alter the separate signal commitment",
    )
    reordered_consumers = copy.deepcopy(first_usage)
    reordered_consumers["selectors"].reverse()
    reordered_model = _model_allocations(reordered_consumers)
    require_exact(
        (
            _model_allocation_sha256(reordered_model),
            _model_origin_signal_commitment(reordered_model),
        ),
        (
            _model_allocation_sha256(first_model),
            _model_origin_signal_commitment(first_model),
        ),
        "selector array order changed stable unit or signal identity",
    )

    moved_declaration = copy.deepcopy(distinct_transition_domains)
    moved_declaration["selectors"].append(
        {
            "events": [],
            "owned_resources": [],
            "selector_id": "SECOND_SELECTOR",
            "state_domains": [],
        }
    )
    declaration_baseline_model = _model_allocations(moved_declaration)
    moved_declaration["selectors"][1]["events"] = moved_declaration["selectors"][0][
        "events"
    ]
    moved_declaration["selectors"][0]["events"] = []
    moved_declaration_model = _model_allocations(moved_declaration)
    require_exact(
        _model_allocation_sha256(declaration_baseline_model),
        _model_allocation_sha256(moved_declaration_model),
        "declaration-selector-independent unit identity",
    )
    require(
        _model_origin_signal_commitment(declaration_baseline_model)
        != _model_origin_signal_commitment(moved_declaration_model),
        "declaration selector movement did not alter the separate origin commitment",
    )

    eleven_consumers = copy.deepcopy(first_usage)
    eleven_consumers["selectors"] = [
        {
            **copy.deepcopy(selector_template),
            "selector_id": f"CONSUMER_{index:02d}",
            "usage": shared_reference,
        }
        for index in range(11)
    ]
    shared_unit = next(
        allocation
        for allocation in _model_allocations(eleven_consumers)
        if allocation.semantic_ref == shared_reference
    )
    require_exact(
        len(
            {
                signal.semantic_location
                for signal in shared_unit.signals
                if signal.evidence_kind == "SELECTOR_USAGE"
            }
        ),
        11,
        "former eleven-consumer usage conflict aggregation",
    )
    require_exact(
        shared_unit.unit_id,
        allocation_unit_id("TYPE", "SharedType", shared_reference),
        "usage-independent unit ID derivation",
    )
    same_identity_different_evidence = ModelAllocation(
        "TYPE",
        "SharedType",
        shared_reference,
        origins=(
            AllocationEvidence(
                "ARTIFACT_REGISTRY_ENTRY",
                "artifact-ref::different-diagnostic-location",
            ),
        ),
        signals=(
            AllocationEvidence(
                "SELECTOR_USAGE",
                "selector-id::DIFFERENT_CONSUMER",
            ),
        ),
    )
    require(
        shared_unit == same_identity_different_evidence
        and hash(shared_unit) == hash(same_identity_different_evidence),
        "origin/signal metadata affected semantic unit equality or hashing",
    )
    require_exact(
        _candidate_allocation_adr_id(
            ModelAllocation(
                "TYPE",
                "UnrouteableSharedType",
                "unrouteable-shared-type::UnrouteableSharedType",
            ),
            accepted_prose_identifiers={
                f"ADR-{index:03d}": set() for index in range(1, 12)
            },
        ),
        "UNMAPPED_SHARED",
        "shared-unit candidate routing must not use an ADR-001 catch-all",
    )
    require_exact(
        _candidate_allocation_adr_id(
            ModelAllocation(
                "SELECTOR",
                "UNKNOWN_SELECTOR",
                "selector-id::UNKNOWN_SELECTOR",
            ),
            accepted_prose_identifiers={
                f"ADR-{index:03d}": set() for index in range(1, 12)
            },
        ),
        "UNMAPPED_SHARED",
        "unknown declaration selector must remain explicitly unmapped",
    )
    return 18


def _run_selector_resource_allocation_self_test() -> int:
    baseline = {
        "actor_profiles": {},
        "artifacts": [],
        "selectors": [
            {
                "events": [
                    {
                        "event_id": "CREATE_SAMPLE",
                        "transition_kind": (
                            "create-sample-transition-kind::CreateSample"
                        ),
                    },
                    {
                        "event_id": "RETIRE_SAMPLE",
                        "transition_kind": (
                            "retire-sample-transition-kind::RetireSample"
                        ),
                    },
                ],
                "owned_resources": [
                    {
                        "owner_selector_id": "SAMPLE",
                        "resource": "SAMPLE.HEAD",
                    }
                ],
                "selector_id": "SAMPLE",
                "state_domains": [
                    {
                        "state_domain": "ROOT",
                        "states": ["ACTIVE", "TERMINAL"],
                    },
                    {
                        "state_domain": "CHILD",
                        "states": ["ABSENT", "LIVE"],
                    },
                ],
            }
        ],
    }
    model = _model_allocations(baseline)
    require(
        {
            ModelAllocation("SELECTOR", "SAMPLE", "selector-id::SAMPLE"),
            ModelAllocation(
                "RESOURCE",
                "SAMPLE.HEAD",
                "resource-id::SAMPLE.HEAD",
            ),
        }.issubset(model),
        "selector/resource allocation self-test lost a first-class identity",
    )
    reordered = copy.deepcopy(baseline)
    reordered["selectors"][0]["events"].reverse()
    reordered["selectors"][0]["state_domains"].reverse()
    for domain in reordered["selectors"][0]["state_domains"]:
        domain["states"].reverse()
    reordered_model = _model_allocations(reordered)
    require_exact(
        (
            _model_allocation_sha256(reordered_model),
            _model_origin_signal_commitment(reordered_model),
        ),
        (
            _model_allocation_sha256(model),
            _model_origin_signal_commitment(model),
        ),
        "event, state-domain, and state array-order-independent identity",
    )
    mutants: list[tuple[str, Any]] = [
        (
            "resource owner mismatch",
            lambda value: value["selectors"][0]["owned_resources"][0].__setitem__(
                "owner_selector_id", "OTHER"
            ),
        ),
        (
            "resource namespace mismatch",
            lambda value: value["selectors"][0]["owned_resources"][0].__setitem__(
                "resource", "OTHER.HEAD"
            ),
        ),
        (
            "duplicate resource identity",
            lambda value: value["selectors"][0]["owned_resources"].append(
                copy.deepcopy(value["selectors"][0]["owned_resources"][0])
            ),
        ),
        (
            "duplicate selector identity",
            lambda value: value["selectors"].append(
                copy.deepcopy(value["selectors"][0])
            ),
        ),
    ]
    for label, mutate in mutants:
        hostile = copy.deepcopy(baseline)
        mutate(hostile)
        try:
            _model_allocations(hostile)
        except ClosureCheckError:
            pass
        else:
            fail(f"selector/resource allocation self-test accepted {label}")
    return 2 + len(mutants)


def _lexicographic_array_indices(length: int) -> Iterator[int]:
    """Yield array indexes by their unpadded decimal segment bytes."""

    if length == 0:
        return
    yield 0

    def descendants(prefix: int) -> Iterator[int]:
        if prefix >= length:
            return
        yield prefix
        for digit in range(10):
            child = prefix * 10 + digit
            if child < length:
                yield from descendants(child)

    for leading_digit in range(1, 10):
        yield from descendants(leading_digit)


def _semantic_shape_pointer_segment(member_name: Any) -> str:
    require(
        type(member_name) is str,
        "semantic shape object member name is not a native JSON string",
    )
    require(
        all(0x20 <= ord(character) <= 0x7E for character in member_name),
        (
            "semantic shape object member name is outside the closed empty-or-"
            "printable-ASCII domain"
        ),
    )
    return member_name.replace("~", "~0").replace("/", "~1")


def _semantic_shape_children(
    pointer: str,
    value: Any,
    depth: int,
) -> Iterator[tuple[str, Any, int]]:
    if type(value) is dict:
        # Retain only parent-independent segments while sorting. Materializing
        # every full child pointer here would multiply the parent-pointer size
        # by object width before the projection-byte bound can reject it.
        members = [
            (
                segment.encode("ascii"),
                key,
                segment,
            )
            for key in value
            for segment in (_semantic_shape_pointer_segment(key),)
        ]
        members.sort(key=lambda item: item[0])

        def object_children() -> Iterator[tuple[str, Any, int]]:
            for _, key, segment in members:
                require(
                    len(pointer) + 1 + len(segment) <= MAX_SEMANTIC_SHAPE_POINTER_CHARS,
                    (
                        "semantic shape JSON pointer exceeds "
                        f"{MAX_SEMANTIC_SHAPE_POINTER_CHARS} characters"
                    ),
                )
                yield f"{pointer}/{segment}", value[key], depth + 1

        return object_children()
    if type(value) is list:

        def array_children() -> Iterator[tuple[str, Any, int]]:
            for index in _lexicographic_array_indices(len(value)):
                segment = str(index)
                require(
                    len(pointer) + 1 + len(segment) <= MAX_SEMANTIC_SHAPE_POINTER_CHARS,
                    (
                        "semantic shape JSON pointer exceeds "
                        f"{MAX_SEMANTIC_SHAPE_POINTER_CHARS} characters"
                    ),
                )
                yield f"{pointer}/{segment}", value[index], depth + 1

        return array_children()
    return iter(())


def _semantic_shape_rows(data: dict[str, Any]) -> Iterator[list[str]]:
    """Yield the v3 pointer/type projection in exact pointer-byte order."""

    pending: list[
        tuple[
            bytes,
            int,
            str,
            Any,
            int,
            Iterator[tuple[str, Any, int]] | None,
        ]
    ] = []
    insertion_order = count()

    def enqueue(
        child: tuple[str, Any, int],
        remaining_siblings: Iterator[tuple[str, Any, int]] | None,
    ) -> None:
        pointer, value, depth = child
        heappush(
            pending,
            (
                pointer.encode("ascii"),
                next(insertion_order),
                pointer,
                value,
                depth,
                remaining_siblings,
            ),
        )

    enqueue(("", data, 0), None)
    while pending:
        _, _, pointer, value, depth, remaining_siblings = heappop(pending)
        if remaining_siblings is not None:
            try:
                next_sibling = next(remaining_siblings)
            except StopIteration:
                pass
            else:
                enqueue(next_sibling, remaining_siblings)
        require(
            depth <= MAX_SEMANTIC_SHAPE_DEPTH,
            (f"semantic shape exceeds {MAX_SEMANTIC_SHAPE_DEPTH} JSON nesting levels"),
        )
        require(
            len(pointer) <= MAX_SEMANTIC_SHAPE_POINTER_CHARS,
            (
                "semantic shape JSON pointer exceeds "
                f"{MAX_SEMANTIC_SHAPE_POINTER_CHARS} characters"
            ),
        )
        require(
            pointer == ""
            or (
                pointer.startswith("/")
                and all(0x20 <= ord(character) <= 0x7E for character in pointer)
            ),
            "semantic shape generated a noncanonical JSON pointer",
        )
        value_type = {
            dict: "object",
            list: "array",
            type(None): "null",
            bool: "boolean",
            int: "integer",
            str: "string",
        }.get(type(value))
        require(
            value_type is not None,
            f"semantic shape contains non-JSON value at {pointer!r}",
        )
        if type(value) is int:
            require(
                abs(value) <= MAX_SAFE_INTEGER,
                f"semantic shape integer is outside the safe range at {pointer!r}",
            )
        elif type(value) is str:
            require(
                all(0x20 <= ord(character) <= 0x7E for character in value),
                (
                    "semantic shape string is outside the empty-or-printable-"
                    f"ASCII domain at {pointer!r}"
                ),
            )
        yield [pointer, value_type]
        children = _semantic_shape_children(pointer, value, depth)
        try:
            first_child = next(children)
        except StopIteration:
            continue
        enqueue(first_child, children)


def _semantic_shape_commitment(
    data: dict[str, Any],
) -> tuple[int, str]:
    """Commit the closed v3 JSON-pointer/type stream without scalar values."""

    require(
        type(data) is dict,
        "semantic shape source must be a native JSON object",
    )
    projection_byte_length = 2
    entry_count = 0
    for row in _semantic_shape_rows(data):
        encoded_row = canonical_bytes(row)
        projection_byte_length += len(encoded_row) + (1 if entry_count else 0)
        entry_count += 1
        require(
            entry_count <= MAX_SEMANTIC_SHAPE_ROWS,
            f"semantic shape exceeds {MAX_SEMANTIC_SHAPE_ROWS} entries",
        )
        require(
            projection_byte_length <= MAX_SEMANTIC_SHAPE_BYTES,
            (f"semantic shape commitment exceeds {MAX_SEMANTIC_SHAPE_BYTES} bytes"),
        )

    digest = sha256()
    digest.update(SEMANTIC_SHAPE_PROJECTION_DOMAIN)
    digest.update(projection_byte_length.to_bytes(8, "big"))
    digest.update(b"[")
    written = 1
    for index, row in enumerate(_semantic_shape_rows(data)):
        if index:
            digest.update(b",")
            written += 1
        encoded_row = canonical_bytes(row)
        digest.update(encoded_row)
        written += len(encoded_row)
    digest.update(b"]")
    written += 1
    require_exact(
        written,
        projection_byte_length,
        "semantic shape two-pass projection byte length",
    )
    return entry_count, digest.hexdigest()


def _run_semantic_shape_self_test() -> int:
    first = {"b": [{"x": 1}], "a": True}
    reordered = {"a": False, "b": [{"x": 9}]}
    require_exact(
        _semantic_shape_commitment(first),
        _semantic_shape_commitment(reordered),
        "semantic shape insertion-order and scalar-value independence",
    )
    expected_pointer_order = [
        "",
        "/",
        "/a",
        "/a/0",
        "/a/1",
        "/a/10",
        "/a/11",
        "/a/2",
        "/a/3",
        "/a/4",
        "/a/5",
        "/a/6",
        "/a/7",
        "/a/8",
        "/a/9",
        "/~0",
        "/~1",
    ]
    require_exact(
        [
            row[0]
            for row in _semantic_shape_rows(
                {
                    "": None,
                    "a": list(range(12)),
                    "~": None,
                    "/": None,
                }
            )
        ],
        expected_pointer_order,
        "semantic shape RFC 6901 root, escaping, and lexical array order",
    )
    require_exact(
        [
            row[0]
            for row in _semantic_shape_rows(
                {
                    "a": {"x": None},
                    "a-": None,
                    "a.": None,
                }
            )
        ],
        ["", "/a", "/a-", "/a.", "/a/x"],
        "semantic shape complete-pointer order across siblings and descendants",
    )
    exact_pointer_source = {"a" * (MAX_SEMANTIC_SHAPE_POINTER_CHARS - 1): None}
    exact_pointer_rows = list(_semantic_shape_rows(exact_pointer_source))
    require_exact(
        len(exact_pointer_rows[1][0]),
        MAX_SEMANTIC_SHAPE_POINTER_CHARS,
        "semantic shape exact maximum pointer length",
    )
    _semantic_shape_commitment(exact_pointer_source)
    shape_vector = SEMANTIC_SHAPE_COMMITMENT_SUITE["fixed_vectors"][
        "representative_types_and_escaping"
    ]
    shape_source_raw = bytes.fromhex(shape_vector["source_canonical_utf8_hex"])
    require_exact(
        len(shape_source_raw),
        shape_vector["source_canonical_utf8_byte_length"],
        "semantic shape v3 artifact-declared source byte length",
    )
    shape_source = parse_json_bytes(
        shape_source_raw,
        label="semantic shape v3 fixed-vector source",
    )
    require_exact(
        shape_source_raw,
        codec_canonical_bytes(shape_source),
        "semantic shape fixed-vector canonical source bytes",
    )
    require_exact(
        list(_semantic_shape_rows(shape_source)),
        shape_vector["expected_projection_rows"],
        "semantic shape v3 artifact-declared projection vector",
    )
    require_exact(
        len(canonical_bytes(shape_vector["expected_projection_rows"])),
        shape_vector["expected_projection_byte_length"],
        "semantic shape v3 artifact-declared projection byte length",
    )
    require_exact(
        _semantic_shape_commitment(shape_source),
        (
            shape_vector["expected_entry_count"],
            shape_vector["expected_sha256"],
        ),
        "semantic shape v3 domain/framing/type-taxonomy vector",
    )
    depth_vector = SEMANTIC_SHAPE_COMMITMENT_SUITE["fixed_vectors"][
        "nesting_depth_boundary"
    ]
    require_exact(
        depth_vector["root_depth"],
        0,
        "semantic shape fixed-vector root depth",
    )

    def depth_boundary_source(array_wrapper_count: int) -> dict[str, Any]:
        nested: Any = None
        for _ in range(array_wrapper_count):
            nested = [nested]
        return {"x": nested}

    accepted_depth_source = depth_boundary_source(
        depth_vector["maximum_accepted_array_wrapper_count"]
    )
    require_exact(
        _semantic_shape_commitment(accepted_depth_source),
        (
            depth_vector["expected_accepted_entry_count"],
            depth_vector["expected_accepted_sha256"],
        ),
        "semantic shape exact maximum-depth fixed vector",
    )
    require_exact(
        len(canonical_bytes(list(_semantic_shape_rows(accepted_depth_source)))),
        depth_vector["expected_accepted_projection_byte_length"],
        "semantic shape maximum-depth projection byte length",
    )
    try:
        _semantic_shape_commitment(
            depth_boundary_source(depth_vector["first_rejected_array_wrapper_count"])
        )
    except ClosureCheckError:
        pass
    else:
        fail("semantic shape accepted the first depth beyond its declared maximum")
    hostile_cases = (
        ({"b": [{"x": 1, "unknown": 0}], "a": True}, "unknown property"),
        ({"b": [{"x": "1"}], "a": True}, "scalar type change"),
    )
    for hostile, label in hostile_cases:
        require(
            _semantic_shape_commitment(hostile) != _semantic_shape_commitment(first),
            f"semantic shape self-test accepted {label}",
        )
    for hostile, label in (
        ([], "non-object source"),
        ({"\N{SNOWMAN}": None}, "Unicode member name"),
        ({"line\nbreak": None}, "control member name"),
        ({"value": "\N{SNOWMAN}"}, "Unicode scalar string"),
        ({"value": "line\nbreak"}, "control scalar string"),
        ({"value": 1.0}, "integral float"),
        ({"value": -0.0}, "negative-zero float"),
        ({"value": MAX_SAFE_INTEGER + 1}, "unsafe positive integer"),
        ({"value": -(MAX_SAFE_INTEGER + 1)}, "unsafe negative integer"),
        ({"a" * MAX_SEMANTIC_SHAPE_POINTER_CHARS: None}, "maximum pointer plus one"),
    ):
        try:
            _semantic_shape_commitment(hostile)
        except ClosureCheckError:
            pass
        else:
            fail(f"semantic shape self-test accepted {label}")
    for raw, label in (
        (b'{"value":1.0}', "fraction-form integral token"),
        (b'{"value":1e0}', "exponent-form integral token"),
        (b'{"value":-0}', "negative-zero integer token"),
        (b'{"value":9007199254740992}', "unsafe positive integer token"),
        (b'{"value":-9007199254740992}', "unsafe negative integer token"),
    ):
        try:
            parsed = parse_json_bytes(raw, label=f"semantic shape hostile {label}")
            require_exact(
                raw,
                codec_canonical_bytes(parsed),
                f"semantic shape hostile {label} canonical bytes",
            )
            _semantic_shape_commitment(parsed)
        except (ClosureCheckError, SelectorClosureCodecError):
            pass
        else:
            fail(f"semantic shape accepted {label}")
    long_parent_wide_object = {
        "p" * 8_000: {f"k{index:05d}": None for index in range(5_000)}
    }
    tracing_was_active = tracemalloc.is_tracing()
    if not tracing_was_active:
        tracemalloc.start()
    trace_baseline_bytes, _ = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    try:
        _semantic_shape_commitment(long_parent_wide_object)
    except ClosureCheckError as error:
        require(
            "semantic shape commitment exceeds" in str(error),
            "semantic shape wide-object regression failed at the wrong bound",
        )
    else:
        fail("semantic shape wide-object regression did not reach its byte bound")
    finally:
        _, trace_peak_bytes = tracemalloc.get_traced_memory()
        if not tracing_was_active:
            tracemalloc.stop()
    streaming_peak_bytes = max(0, trace_peak_bytes - trace_baseline_bytes)
    require(
        streaming_peak_bytes <= 8 * 1024 * 1024,
        (
            "semantic shape long-parent wide-object traversal retained "
            f"{streaming_peak_bytes} bytes before its projection-bound rejection"
        ),
    )
    return 12 + len(hostile_cases) + 10


def _validate_allocation_coverage(
    *,
    status: Any,
    model: set[ModelAllocation],
    declared: set[ModelAllocation],
    allocation_identifier_keys: set[ExtractedIdentifier],
    exclusion_identifier_keys: set[ExtractedIdentifier],
    blocking_exclusion_keys: set[ExtractedIdentifier],
    provenance_reviewed: bool,
    require_complete: bool,
) -> None:
    require(
        status in {"COMPLETE", "INCOMPLETE_FAIL_CLOSED"},
        "allocation oracle has an invalid status",
    )
    extra_model_allocations = declared - model
    require(
        not extra_model_allocations,
        (
            "ADR allocation oracle contains entries absent from the model: "
            f"count={len(extra_model_allocations)} "
            f"sample={sorted(extra_model_allocations)[:3]}"
        ),
    )
    overlap = allocation_identifier_keys & exclusion_identifier_keys
    require(
        not overlap,
        (
            "ADR identifiers cannot be both allocated and excluded: "
            f"count={len(overlap)} sample={sorted(overlap)[:3]}"
        ),
    )

    missing_model = model - declared
    missing_by_kind = {
        kind: sum(1 for allocation in missing_model if allocation.kind == kind)
        for kind in sorted(ADR_ALLOCATION_KINDS)
    }
    complete = (
        not missing_model
        and not extra_model_allocations
        and not blocking_exclusion_keys
        and provenance_reviewed
    )
    require_exact(
        status == "COMPLETE",
        complete,
        "allocation oracle status/content parity",
    )
    if require_complete:
        missing_summary = " ".join(
            f"missing {kind}={missing_by_kind[kind]}" for kind in ALLOCATION_KINDS
        )
        require(
            complete,
            (
                "ADR allocation oracle is incomplete and fails closed: "
                f"{missing_summary} model provenance entries; "
                f"extra_model_rows={len(extra_model_allocations)}; "
                f"blocking_exclusions={len(blocking_exclusion_keys)}; "
                f"provenance_reviewed={provenance_reviewed}"
            ),
        )


def _run_allocation_coverage_self_test() -> int:
    """Prove both model and provenance omissions fail closed."""

    type_allocation = ModelAllocation(
        "TYPE",
        "SyntheticType",
        "synthetic-type::SyntheticType",
    )
    event_allocation = ModelAllocation(
        "EVENT",
        "CREATE_SYNTHETIC",
        "synthetic-transition-kind::CreateSynthetic",
    )
    state_allocation = ModelAllocation(
        "STATE",
        "ACTIVE",
        "state-id::SYNTHETIC.ROOT.ACTIVE",
    )
    profile_allocation = ModelAllocation(
        "PROFILE",
        "synthetic_profile",
        "/synthetic_profile",
    )
    model = {
        type_allocation,
        event_allocation,
        profile_allocation,
        state_allocation,
    }
    allocation_keys = {
        ("ADR-001", "SyntheticType"),
        ("ADR-001", "CREATE_SYNTHETIC"),
        ("ADR-001", "ACTIVE"),
        ("ADR-001", "synthetic_profile"),
    }
    _validate_allocation_coverage(
        status="COMPLETE",
        model=model,
        declared=set(model),
        allocation_identifier_keys=allocation_keys,
        exclusion_identifier_keys=set(),
        blocking_exclusion_keys=set(),
        provenance_reviewed=True,
        require_complete=True,
    )
    try:
        _validate_allocation_coverage(
            status="COMPLETE",
            model=model,
            declared=set(model),
            allocation_identifier_keys=allocation_keys,
            exclusion_identifier_keys=set(),
            blocking_exclusion_keys=set(),
            provenance_reviewed=False,
            require_complete=False,
        )
    except ClosureCheckError:
        pass
    else:
        fail("allocation-oracle self-test bypassed semantic provenance review")
    _validate_allocation_coverage(
        status="INCOMPLETE_FAIL_CLOSED",
        model=model,
        declared=set(model),
        allocation_identifier_keys=allocation_keys,
        exclusion_identifier_keys=set(),
        blocking_exclusion_keys=set(),
        provenance_reviewed=False,
        require_complete=False,
    )

    try:
        _validate_allocation_coverage(
            status="COMPLETE",
            model=model,
            declared=model - {event_allocation},
            allocation_identifier_keys=allocation_keys
            - {("ADR-001", "CREATE_SYNTHETIC")},
            exclusion_identifier_keys=set(),
            blocking_exclusion_keys=set(),
            provenance_reviewed=True,
            require_complete=True,
        )
    except ClosureCheckError:
        pass
    else:
        fail("allocation-oracle self-test accepted a deleted ADR allocation")

    try:
        _validate_allocation_coverage(
            status="COMPLETE",
            model=model,
            declared=model - {profile_allocation},
            allocation_identifier_keys=allocation_keys
            - {("ADR-001", "synthetic_profile")},
            exclusion_identifier_keys=set(),
            blocking_exclusion_keys=set(),
            provenance_reviewed=True,
            require_complete=True,
        )
    except ClosureCheckError:
        pass
    else:
        fail("allocation-oracle self-test accepted a deleted PROFILE allocation")

    try:
        _validate_allocation_coverage(
            status="COMPLETE",
            model=model - {event_allocation},
            declared=set(model),
            allocation_identifier_keys=allocation_keys,
            exclusion_identifier_keys=set(),
            blocking_exclusion_keys=set(),
            provenance_reviewed=True,
            require_complete=True,
        )
    except ClosureCheckError:
        pass
    else:
        fail("allocation-oracle self-test accepted a deleted model event")

    extra_allocation = ModelAllocation(
        "TYPE",
        "UnknownSyntheticType",
        "unknown-synthetic-type::UnknownSyntheticType",
    )
    try:
        _validate_allocation_coverage(
            status="COMPLETE",
            model=model,
            declared=model | {extra_allocation},
            allocation_identifier_keys=allocation_keys,
            exclusion_identifier_keys=set(),
            blocking_exclusion_keys=set(),
            provenance_reviewed=True,
            require_complete=True,
        )
    except ClosureCheckError:
        pass
    else:
        fail("allocation-oracle self-test accepted an extra model allocation")

    duplicate_identifier_keys = set(allocation_keys)
    try:
        _validate_allocation_coverage(
            status="COMPLETE",
            model=model,
            declared=set(model),
            allocation_identifier_keys=duplicate_identifier_keys,
            exclusion_identifier_keys={("ADR-001", "CREATE_SYNTHETIC")},
            blocking_exclusion_keys=set(),
            provenance_reviewed=True,
            require_complete=True,
        )
    except ClosureCheckError:
        pass
    else:
        fail("allocation-oracle self-test accepted allocated/excluded overlap")

    try:
        _validate_allocation_coverage(
            status="INCOMPLETE_FAIL_CLOSED",
            model=model,
            declared=set(model),
            allocation_identifier_keys=allocation_keys,
            exclusion_identifier_keys=set(),
            blocking_exclusion_keys=set(),
            provenance_reviewed=True,
            require_complete=False,
        )
    except ClosureCheckError:
        pass
    else:
        fail("allocation-oracle self-test accepted stale incomplete status")
    return 8


def _read_bound_adr_source(
    *,
    path_text: str,
    byte_length: Any,
    source_sha256: Any,
    label: str,
    snapshots: dict[Path, bytes],
    source_file_identities: dict[tuple[int, int], Path],
) -> str:
    """Read and bind one non-aliased main or module source."""

    require(
        isinstance(byte_length, int)
        and not isinstance(byte_length, bool)
        and 0 < byte_length <= MAX_ADR_BYTES,
        f"{label}: invalid bounded byte length",
    )
    require(
        isinstance(source_sha256, str) and SHA256_HEX.fullmatch(source_sha256),
        f"{label}: invalid SHA-256",
    )
    require(isinstance(path_text, str), f"{label}: path must be a string")
    path = Path(path_text)
    require(
        not path.is_absolute() and ".." not in path.parts,
        f"{label}: path escapes the repository",
    )
    require(path not in snapshots, f"{label}: source path aliases another source")
    raw = read_bounded_regular_file(
        ROOT / path,
        maximum_bytes=MAX_ADR_BYTES,
        label=label,
    )
    require_exact(len(raw), byte_length, f"{label}: byte length")
    require_exact(sha256(raw).hexdigest(), source_sha256, f"{label}: source digest")
    source_stat = os.stat(ROOT / path, follow_symlinks=False)
    source_identity = (source_stat.st_dev, source_stat.st_ino)
    require(
        source_identity not in source_file_identities,
        (f"{label}: file aliases {source_file_identities.get(source_identity)}"),
    )
    source_file_identities[source_identity] = path
    snapshots[path] = raw
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        fail(f"{label}: invalid UTF-8: {error}")


def _validate_adr_allocation_oracle(
    data: dict[str, Any],
    *,
    require_complete: bool,
) -> dict[Path, bytes]:
    oracle_keys = {
        "allocation_review_profile",
        "allocations",
        "claim_boundary",
        "document_row_commitment",
        "documents",
        "exclusions",
        "model_allocation_count",
        "model_allocation_sha256",
        "provenance_review",
        "required_kinds",
        "semantic_review_subject",
        "semantic_shape_entry_count",
        "semantic_shape_sha256",
        "status",
    }
    oracle = _require_closed_shape(
        data["adr_allocation_oracle"],
        required=oracle_keys,
        allowed=oracle_keys,
        label="adr_allocation_oracle",
    )
    require_exact(
        oracle["claim_boundary"],
        "NON_NORMATIVE_B01_SEMANTIC_ALLOCATION_PROVENANCE_ONLY",
        "allocation oracle claim boundary",
    )
    _require_closed_shape(
        oracle["document_row_commitment"],
        required=DOCUMENT_ROW_COMMITMENT_KEYS,
        allowed=DOCUMENT_ROW_COMMITMENT_KEYS,
        label="adr_allocation_oracle.document_row_commitment",
    )
    require_exact(
        oracle["document_row_commitment"],
        DOCUMENT_ROW_COMMITMENT,
        "allocation oracle document row commitment suite",
    )
    require_exact(
        oracle["required_kinds"],
        list(ALLOCATION_KINDS),
        "allocation oracle required kinds",
    )
    require(
        isinstance(oracle["model_allocation_count"], int)
        and not isinstance(oracle["model_allocation_count"], bool)
        and oracle["model_allocation_count"] > 0,
        "allocation oracle has an invalid model allocation count",
    )
    require(
        isinstance(oracle["model_allocation_sha256"], str)
        and SHA256_HEX.fullmatch(oracle["model_allocation_sha256"]),
        "allocation oracle has an invalid model allocation SHA-256",
    )
    require_exact(
        oracle["model_allocation_count"],
        EXPECTED_MODEL_ALLOCATION_COUNT,
        "reviewed model allocation count",
    )
    require_exact(
        oracle["model_allocation_sha256"],
        EXPECTED_MODEL_ALLOCATION_SHA256,
        "reviewed model allocation digest",
    )
    require(
        isinstance(oracle["semantic_shape_entry_count"], int)
        and not isinstance(oracle["semantic_shape_entry_count"], bool)
        and oracle["semantic_shape_entry_count"] > 0,
        "allocation oracle has an invalid semantic shape entry count",
    )
    require(
        isinstance(oracle["semantic_shape_sha256"], str)
        and SHA256_HEX.fullmatch(oracle["semantic_shape_sha256"]),
        "allocation oracle has an invalid semantic shape SHA-256",
    )
    require_exact(
        oracle["semantic_shape_entry_count"],
        EXPECTED_SEMANTIC_SHAPE_ENTRY_COUNT,
        "reviewed semantic shape entry count",
    )
    require_exact(
        oracle["semantic_shape_sha256"],
        EXPECTED_SEMANTIC_SHAPE_SHA256,
        "reviewed semantic shape digest",
    )
    allocation_review_profile = _require_closed_shape(
        oracle["allocation_review_profile"],
        required=ALLOCATION_REVIEW_PROFILE_KEYS,
        allowed=ALLOCATION_REVIEW_PROFILE_KEYS,
        label="adr_allocation_oracle.allocation_review_profile",
    )
    require_exact(
        {
            "allocation_identity_commitment_suite": allocation_review_profile[
                "allocation_identity_commitment_suite"
            ],
            "allocation_schema_id": allocation_review_profile["allocation_schema_id"],
            "model_projection_schema": allocation_review_profile[
                "model_projection_schema"
            ],
            "model_origin_signal_projection_schema": allocation_review_profile[
                "model_origin_signal_projection_schema"
            ],
            "required_kinds": allocation_review_profile["required_kinds"],
            "resource_closure_schema": allocation_review_profile[
                "resource_closure_schema"
            ],
            "schema": allocation_review_profile["schema"],
            "semantic_shape_commitment_suite": allocation_review_profile[
                "semantic_shape_commitment_suite"
            ],
            "semantic_shape_projection_schema": allocation_review_profile[
                "semantic_shape_projection_schema"
            ],
        },
        {
            "allocation_identity_commitment_suite": (
                ALLOCATION_IDENTITY_COMMITMENT_SUITE
            ),
            "allocation_schema_id": ("ncp.b01-selector-allocation-authoring.v1"),
            "model_projection_schema": MODEL_ALLOCATION_PROJECTION_SCHEMA,
            "model_origin_signal_projection_schema": (
                MODEL_ORIGIN_SIGNAL_PROJECTION_SCHEMA
            ),
            "required_kinds": list(ALLOCATION_KINDS),
            "resource_closure_schema": RESOURCE_CLOSURE_PROJECTION_SCHEMA,
            "schema": ALLOCATION_REVIEW_PROFILE_SCHEMA,
            "semantic_shape_commitment_suite": SEMANTIC_SHAPE_COMMITMENT_SUITE,
            "semantic_shape_projection_schema": (SEMANTIC_SHAPE_PROJECTION_SCHEMA),
        },
        "allocation review profile suite",
    )
    require_exact(
        {
            "model_allocation_count": allocation_review_profile[
                "model_allocation_count"
            ],
            "model_allocation_sha256": allocation_review_profile[
                "model_allocation_sha256"
            ],
            "model_origin_signal_row_count": allocation_review_profile[
                "model_origin_signal_row_count"
            ],
            "model_origin_signal_sha256": allocation_review_profile[
                "model_origin_signal_sha256"
            ],
            "resource_closure_row_count": allocation_review_profile[
                "resource_closure_row_count"
            ],
            "resource_closure_sha256": allocation_review_profile[
                "resource_closure_sha256"
            ],
            "semantic_shape_entry_count": allocation_review_profile[
                "semantic_shape_entry_count"
            ],
            "semantic_shape_sha256": allocation_review_profile["semantic_shape_sha256"],
        },
        {
            "model_allocation_count": oracle["model_allocation_count"],
            "model_allocation_sha256": oracle["model_allocation_sha256"],
            "model_origin_signal_row_count": len(_model_allocations(data)),
            "model_origin_signal_sha256": _model_origin_signal_commitment(
                _model_allocations(data)
            )[1],
            "resource_closure_row_count": data["closure_commitments"][
                "resource_closure"
            ]["row_count"],
            "resource_closure_sha256": data["closure_commitments"]["resource_closure"][
                "sha256"
            ],
            "semantic_shape_entry_count": oracle["semantic_shape_entry_count"],
            "semantic_shape_sha256": oracle["semantic_shape_sha256"],
        },
        "allocation review profile model metrics",
    )
    require_exact(
        allocation_review_profile["model_origin_signal_row_count"],
        EXPECTED_MODEL_ORIGIN_SIGNAL_ROW_COUNT,
        "reviewed model origin/signal row count",
    )
    require_exact(
        allocation_review_profile["model_origin_signal_sha256"],
        EXPECTED_MODEL_ORIGIN_SIGNAL_SHA256,
        "reviewed model origin/signal digest",
    )
    require(
        isinstance(allocation_review_profile["allocation_schema_byte_length"], int)
        and not isinstance(
            allocation_review_profile["allocation_schema_byte_length"], bool
        )
        and 0
        < allocation_review_profile["allocation_schema_byte_length"]
        <= MAX_ALLOCATION_SCHEMA_BYTES
        and isinstance(allocation_review_profile["allocation_schema_sha256"], str)
        and SHA256_HEX.fullmatch(allocation_review_profile["allocation_schema_sha256"]),
        "allocation review profile has invalid schema provenance",
    )
    semantic_review_subject = _require_closed_shape(
        oracle["semantic_review_subject"],
        required=SEMANTIC_REVIEW_SUBJECT_KEYS,
        allowed=SEMANTIC_REVIEW_SUBJECT_KEYS,
        label="adr_allocation_oracle.semantic_review_subject",
    )
    require_exact(
        {key: semantic_review_subject[key] for key in SEMANTIC_REVIEW_SUBJECT_SUITE},
        SEMANTIC_REVIEW_SUBJECT_SUITE,
        "allocation semantic review subject suite",
    )
    require(
        isinstance(semantic_review_subject["byte_length"], int)
        and not isinstance(semantic_review_subject["byte_length"], bool)
        and semantic_review_subject["byte_length"] > 0,
        "allocation semantic review subject has an invalid byte length",
    )
    require(
        isinstance(semantic_review_subject["sha256"], str)
        and SHA256_HEX.fullmatch(semantic_review_subject["sha256"]),
        "allocation semantic review subject has an invalid SHA-256",
    )
    documents = oracle["documents"]
    require(isinstance(documents, list), "allocation documents must be an array")
    require(
        all(isinstance(document, dict) for document in documents),
        "allocation documents must contain objects",
    )
    require_exact(
        [document.get("path") for document in documents],
        list(ADR_ALLOCATION_PATHS),
        "allocation ADR paths",
    )
    require_exact(
        [document.get("adr_id") for document in documents],
        [f"ADR-{index:03d}" for index in range(1, 12)],
        "allocation ADR IDs",
    )
    require_exact(
        [document.get("allocation_anchor_id") for document in documents],
        list(ADR_ALLOCATION_ANCHOR_IDS),
        "allocation ADR stable anchors",
    )
    require_exact(
        [
            tuple(
                module.get("path")
                for module in document.get("modules", [])
                if isinstance(module, dict)
            )
            for document in documents
        ],
        list(ADR_ALLOCATION_MODULE_PATHS),
        "allocation ADR ordered module paths",
    )
    document_anchors: dict[str, str] = {}
    document_ids: set[str] = set()
    document_snapshots: dict[Path, bytes] = {}
    source_file_identities: dict[tuple[int, int], Path] = {}
    document_corpus_bytes = 0
    for index, document in enumerate(documents):
        label = f"adr_allocation_oracle.documents[{index}]"
        _require_closed_shape(
            document,
            required=DOCUMENT_KEYS,
            allowed=DOCUMENT_KEYS,
            label=label,
        )
        adr_id = document["adr_id"]
        require(
            isinstance(adr_id, str) and re.fullmatch(r"ADR-[0-9]{3}", adr_id),
            f"{label}: invalid ADR ID",
        )
        require(adr_id not in document_ids, f"{label}: duplicate ADR ID")
        document_ids.add(adr_id)
        expected_anchor = ADR_ALLOCATION_ANCHOR_BY_ID[adr_id]
        require_exact(
            document["allocation_anchor_id"],
            expected_anchor,
            f"{label}: stable allocation anchor",
        )
        require(
            isinstance(document["allocation_row_count"], int)
            and not isinstance(document["allocation_row_count"], bool)
            and document["allocation_row_count"] >= 0,
            f"{label}: invalid allocation row count",
        )
        require(
            isinstance(document["exclusion_row_count"], int)
            and not isinstance(document["exclusion_row_count"], bool)
            and document["exclusion_row_count"] >= 0,
            f"{label}: invalid exclusion row count",
        )
        for digest_key in ("allocation_rows_sha256", "exclusion_rows_sha256"):
            require(
                isinstance(document[digest_key], str)
                and SHA256_HEX.fullmatch(document[digest_key]),
                f"{label}: invalid {digest_key}",
            )
        require(
            document["allocation_row_count"] + document["exclusion_row_count"]
            <= MAX_ALLOCATION_ROWS,
            f"{label}: row commitments exceed the bounded inventory",
        )
        main_text = _read_bound_adr_source(
            path_text=document["path"],
            byte_length=document["byte_length"],
            source_sha256=document["sha256"],
            label=f"{adr_id} allocation main source",
            snapshots=document_snapshots,
            source_file_identities=source_file_identities,
        )
        document_corpus_bytes += document["byte_length"]
        modules = document["modules"]
        require(isinstance(modules, list), f"{label}: modules must be an array")
        require_exact(
            tuple(module.get("path") for module in modules),
            ADR_ALLOCATION_MODULE_PATHS[index],
            f"{label}: ordered module paths",
        )
        for module_index, module in enumerate(modules):
            module_label = f"{label}.modules[{module_index}]"
            _require_closed_shape(
                module,
                required=DOCUMENT_MODULE_KEYS,
                allowed=DOCUMENT_MODULE_KEYS,
                label=module_label,
            )
            module_text = _read_bound_adr_source(
                path_text=module["path"],
                byte_length=module["byte_length"],
                source_sha256=module["sha256"],
                label=f"{adr_id} allocation module {module_index}",
                snapshots=document_snapshots,
                source_file_identities=source_file_identities,
            )
            require(
                not ALLOCATION_ANCHOR_RE.findall(module_text),
                (
                    f"{module_label}: stable allocation anchor must remain "
                    "in the main ADR"
                ),
            )
            document_corpus_bytes += module["byte_length"]
        require(
            document_corpus_bytes <= MAX_ADR_CORPUS_BYTES,
            (f"allocation ADR corpus exceeds {MAX_ADR_CORPUS_BYTES} bytes"),
        )
        source_set = _require_closed_shape(
            document["source_set"],
            required=DOCUMENT_SOURCE_SET_KEYS,
            allowed=DOCUMENT_SOURCE_SET_KEYS,
            label=f"{label}.source_set",
        )
        require_exact(
            {key: source_set[key] for key in ADR_SOURCE_SET_SUITE},
            ADR_SOURCE_SET_SUITE,
            f"{label}: source-set suite",
        )
        require(
            isinstance(source_set["sha256"], str)
            and SHA256_HEX.fullmatch(source_set["sha256"]),
            f"{label}: invalid source-set SHA-256",
        )
        require_exact(
            source_set["sha256"],
            adr_source_set_sha256(
                adr_id=adr_id,
                path=document["path"],
                byte_length=document["byte_length"],
                source_sha256=document["sha256"],
                modules=modules,
            ),
            f"{label}: ordered source-set digest",
        )
        document_anchors[adr_id] = _extract_allocation_anchor(
            main_text,
            expected_anchor_id=expected_anchor,
            label=adr_id,
        )
    allocations = oracle["allocations"]
    require(isinstance(allocations, list), "allocations must be an array")
    declared_rows: list[ModelAllocation] = []
    allocation_order: list[tuple[str, str, str, str, str, str]] = []
    allocation_identifier_keys: set[ExtractedIdentifier] = set()
    for index, allocation in enumerate(allocations):
        label = f"adr_allocation_oracle.allocations[{index}]"
        _require_closed_shape(
            allocation,
            required=ALLOCATION_ROW_KEYS,
            allowed=ALLOCATION_ROW_KEYS,
            label=label,
        )
        adr_id = allocation["adr_id"]
        kind = allocation["kind"]
        exact_name = allocation["exact_name"]
        semantic_ref = allocation["semantic_ref"]
        unit_id = allocation["unit_id"]
        require(adr_id in document_ids, f"{label}: unknown ADR ID")
        require(
            isinstance(kind, str) and kind in ADR_ALLOCATION_KINDS,
            f"{label}: invalid kind",
        )
        require(
            isinstance(exact_name, str)
            and (
                RESOURCE_EXACT_NAME.fullmatch(exact_name)
                if kind == "RESOURCE"
                else re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", exact_name)
            ),
            f"{label}: invalid exact name",
        )
        require(
            isinstance(semantic_ref, str) and 3 <= len(semantic_ref) <= 1024,
            f"{label}: invalid semantic reference",
        )
        if kind == "PROFILE":
            require(
                (
                    PROFILE_PATH_SEMANTIC_REF.fullmatch(semantic_ref) is not None
                    and "//" not in semantic_ref
                )
                or PROFILE_ID_SEMANTIC_REF.fullmatch(semantic_ref) is not None
                or PROFILE_REFERENCE_SEMANTIC_REF.fullmatch(semantic_ref) is not None,
                f"{label}: PROFILE semantic reference is not stable",
            )
        elif kind == "RESOURCE":
            resource_match = RESOURCE_SEMANTIC_REF.fullmatch(semantic_ref)
            require(
                resource_match is not None and resource_match.group(1) == exact_name,
                f"{label}: RESOURCE semantic reference mismatch",
            )
        elif kind == "SELECTOR":
            selector_match = SELECTOR_SEMANTIC_REF.fullmatch(semantic_ref)
            require(
                selector_match is not None and selector_match.group(1) == exact_name,
                f"{label}: SELECTOR semantic reference mismatch",
            )
        elif kind in {"EVENT", "TYPE"}:
            require(
                ALLOCATION_REF.fullmatch(semantic_ref) is not None,
                f"{label}: {kind} semantic reference must be an allocation reference",
            )
            if kind == "TYPE":
                require_exact(
                    semantic_ref.split("::", 1)[1],
                    exact_name,
                    f"{label}: TYPE exact-name binding",
                )
        elif kind == "STATE":
            state_match = STATE_SEMANTIC_REF.fullmatch(semantic_ref)
            require(
                state_match is not None and state_match.group(3) == exact_name,
                f"{label}: STATE semantic reference mismatch",
            )
        require(
            isinstance(unit_id, str) and SHA256_HEX.fullmatch(unit_id) is not None,
            f"{label}: invalid unit ID",
        )
        require_exact(
            unit_id,
            allocation_unit_id(kind, exact_name, semantic_ref),
            f"{label}: derived unit ID",
        )
        require_exact(
            allocation["source_anchor"],
            document_anchors[adr_id],
            f"{label}: source anchor",
        )
        identifier_key = (adr_id, exact_name)
        declared_rows.append(ModelAllocation(kind, exact_name, semantic_ref))
        allocation_order.append(
            (
                adr_id,
                allocation["source_anchor"],
                kind,
                exact_name,
                semantic_ref,
                unit_id,
            )
        )
        allocation_identifier_keys.add(identifier_key)
    require_exact(
        allocation_order,
        sorted(allocation_order),
        "allocation provenance order",
    )
    require_unique(declared_rows, "allocation provenance model entries")
    declared = set(declared_rows)

    exclusions = oracle["exclusions"]
    require(isinstance(exclusions, list), "exclusions must be an array")
    exclusion_identifier_rows: list[ExtractedIdentifier] = []
    exclusion_order: list[tuple[str, str, str, str]] = []
    blocking_exclusion_keys: set[ExtractedIdentifier] = set()
    for index, exclusion in enumerate(exclusions):
        label = f"adr_allocation_oracle.exclusions[{index}]"
        _require_closed_shape(
            exclusion,
            required=EXCLUSION_ROW_KEYS,
            allowed=EXCLUSION_ROW_KEYS,
            label=label,
        )
        adr_id = exclusion["adr_id"]
        exact_name = exclusion["exact_name"]
        classification = exclusion["classification"]
        reason = exclusion["reason"]
        require(adr_id in document_ids, f"{label}: unknown ADR ID")
        require(
            isinstance(exact_name, str)
            and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", exact_name),
            f"{label}: invalid exact name",
        )
        require(
            isinstance(classification, str)
            and classification in ADR_EXCLUSION_CLASSIFICATIONS,
            f"{label}: invalid classification",
        )
        require(
            isinstance(reason, str)
            and bool(reason.strip())
            and reason == reason.strip()
            and len(reason) <= 1024,
            f"{label}: exclusion reason must be nonempty and trimmed",
        )
        require_exact(
            exclusion["source_anchor"],
            document_anchors[adr_id],
            f"{label}: source anchor",
        )
        identifier_key = (adr_id, exact_name)
        exclusion_identifier_rows.append(identifier_key)
        exclusion_order.append(
            (
                adr_id,
                exclusion["source_anchor"],
                exact_name,
                classification,
            )
        )
        if classification in BLOCKING_ADR_EXCLUSION_CLASSIFICATIONS:
            blocking_exclusion_keys.add(identifier_key)
    require_exact(
        exclusion_order,
        sorted(exclusion_order),
        "allocation provenance exclusion order",
    )
    require_unique(
        exclusion_identifier_rows,
        "allocation provenance exclusion identifiers",
    )
    for index, document in enumerate(documents):
        adr_id = document["adr_id"]
        allocation_rows = [
            allocation for allocation in allocations if allocation["adr_id"] == adr_id
        ]
        exclusion_rows = [
            exclusion for exclusion in exclusions if exclusion["adr_id"] == adr_id
        ]
        label = f"adr_allocation_oracle.documents[{index}]"
        require_exact(
            len(allocation_rows),
            document["allocation_row_count"],
            f"{label}: external allocation row count",
        )
        require_exact(
            document_rows_sha256(
                allocation_rows,
                row_kind="allocations",
            ),
            document["allocation_rows_sha256"],
            f"{label}: external allocation row digest",
        )
        require_exact(
            len(exclusion_rows),
            document["exclusion_row_count"],
            f"{label}: external exclusion row count",
        )
        require_exact(
            document_rows_sha256(
                exclusion_rows,
                row_kind="exclusions",
            ),
            document["exclusion_rows_sha256"],
            f"{label}: external exclusion row digest",
        )

    provenance_review = _require_closed_shape(
        oracle["provenance_review"],
        required=PROVENANCE_REVIEW_KEYS,
        allowed=PROVENANCE_REVIEW_KEYS,
        label="adr_allocation_oracle.provenance_review",
    )
    require_exact(
        {key: provenance_review[key] for key in PROVENANCE_REVIEW_SUITE},
        PROVENANCE_REVIEW_SUITE,
        "allocation provenance review suite",
    )
    require(
        provenance_review["status"] in {"NOT_REVIEWED", "REVIEWED"},
        "allocation provenance review has an unknown status",
    )
    require(
        isinstance(provenance_review["reviewed_assignment_sha256"], str)
        and SHA256_HEX.fullmatch(provenance_review["reviewed_assignment_sha256"]),
        "allocation provenance review has an invalid assignment SHA-256",
    )
    provenance_reviewed = provenance_review["status"] == "REVIEWED"
    require_exact(
        provenance_review["reviewed_assignment_sha256"],
        (
            provenance_assignment_sha256(
                documents,
                allocations,
                exclusions,
                allocation_review_profile,
                semantic_review_subject,
            )
            if provenance_reviewed
            else "0" * 64
        ),
        "allocation provenance review assignment digest",
    )

    model = _model_allocations(data)
    require_exact(
        len(model),
        oracle["model_allocation_count"],
        "allocation oracle model allocation count",
    )
    require_exact(
        _model_allocation_sha256(model),
        oracle["model_allocation_sha256"],
        "allocation oracle model allocation digest",
    )
    shape_entry_count, shape_digest = _semantic_shape_commitment(data)
    require_exact(
        shape_entry_count,
        oracle["semantic_shape_entry_count"],
        "allocation oracle semantic shape entry count",
    )
    require_exact(
        shape_digest,
        oracle["semantic_shape_sha256"],
        "allocation oracle semantic shape digest",
    )
    require_exact(
        semantic_review_subject_commitment(data),
        semantic_review_subject,
        "allocation oracle semantic review subject",
    )
    _validate_allocation_coverage(
        status=oracle["status"],
        model=model,
        declared=declared,
        allocation_identifier_keys=allocation_identifier_keys,
        exclusion_identifier_keys=set(exclusion_identifier_rows),
        blocking_exclusion_keys=blocking_exclusion_keys,
        provenance_reviewed=provenance_reviewed,
        require_complete=require_complete,
    )
    _verify_adr_snapshots_unchanged(document_snapshots)
    return document_snapshots


def _verify_adr_snapshots_unchanged(
    snapshots: dict[Path, bytes],
) -> None:
    source_file_identities: dict[tuple[int, int], Path] = {}
    for path, expected in snapshots.items():
        current = read_bounded_regular_file(
            ROOT / path,
            maximum_bytes=MAX_ADR_BYTES,
            label=f"{path} allocation source stability check",
        )
        require(
            current == expected,
            f"{path}: ADR changed during selector closure validation",
        )
        source_stat = os.stat(ROOT / path, follow_symlinks=False)
        source_identity = (source_stat.st_dev, source_stat.st_ino)
        require(
            source_identity not in source_file_identities,
            (
                f"{path}: ADR source aliases "
                f"{source_file_identities.get(source_identity)}"
            ),
        )
        source_file_identities[source_identity] = path


def _selector_unreachable_state_rows(data: dict[str, Any]) -> set[str]:
    unreachable: set[str] = set()
    for selector in data["selectors"]:
        transitions_by_domain: dict[str, set[tuple[str, str]]] = {
            state_domain["state_domain"]: set()
            for state_domain in selector["state_domains"]
        }
        for edge in selector["state_edge_catalog"]:
            transitions_by_domain[edge["state_domain"]].add(
                (edge["from_state"], edge["to_state"])
            )
        for event in selector["events"]:
            for partition in event["partition_effects"]:
                for branch in partition["branches"]:
                    transitions_by_domain[partition["state_domain"]].add(
                        (branch["from_state"], branch["to_state"])
                    )
        unreachable.update(
            _unreachable_state_rows(
                selector_id=selector["selector_id"],
                state_domains=selector["state_domains"],
                transitions_by_domain=transitions_by_domain,
            )
        )
    return unreachable


def _selector_terminal_liveness_rows(
    data: dict[str, Any],
) -> tuple[set[str], set[str]]:
    states_without_terminal_path: set[str] = set()
    terminal_escape_transitions: set[str] = set()
    for selector in data["selectors"]:
        transitions_by_domain: dict[str, set[tuple[str, str]]] = {
            state_domain["state_domain"]: set()
            for state_domain in selector["state_domains"]
        }
        for edge in selector["state_edge_catalog"]:
            transitions_by_domain[edge["state_domain"]].add(
                (edge["from_state"], edge["to_state"])
            )
        for event in selector["events"]:
            for partition in event["partition_effects"]:
                for branch in partition["branches"]:
                    transitions_by_domain[partition["state_domain"]].add(
                        (branch["from_state"], branch["to_state"])
                    )
        missing, escapes = _terminal_liveness_rows(
            selector_id=selector["selector_id"],
            state_domains=selector["state_domains"],
            transitions_by_domain=transitions_by_domain,
        )
        states_without_terminal_path.update(missing)
        terminal_escape_transitions.update(escapes)
    return states_without_terminal_path, terminal_escape_transitions


def _product_states_without_terminal_path(
    *,
    initial_state: tuple[str, ...],
    transitions: set[tuple[tuple[str, ...], tuple[str, ...]]],
    terminal_states: set[tuple[str, ...]],
) -> set[tuple[str, ...]]:
    """Return reachable product states with no modeled terminal path."""

    reachable = {initial_state}
    while True:
        successor = reachable | {
            target for source, target in transitions if source in reachable
        }
        if successor == reachable:
            break
        reachable = successor

    can_reach_terminal = reachable & terminal_states
    while True:
        predecessor_closure = can_reach_terminal | {
            source
            for source, target in transitions
            if source in reachable and target in can_reach_terminal
        }
        if predecessor_closure == can_reach_terminal:
            break
        can_reach_terminal = predecessor_closure
    return reachable - can_reach_terminal


def _observer_grant_request_product_context(
    data: dict[str, Any],
) -> dict[str, Any]:
    """Resolve the legacy or split request-product state dimensions."""

    selector = next(
        (
            item
            for item in data["selectors"]
            if item["selector_id"] == "OBSERVER_ADMISSION"
        ),
        None,
    )
    require(selector is not None, "missing OBSERVER_ADMISSION selector")
    domains = {item["state_domain"]: item for item in selector["state_domains"]}
    split_state_domain_ids = set(OBSERVER_GRANT_REQUEST_SPLIT_PRODUCT_DOMAINS[:-1])
    present_split_state_domain_ids = split_state_domain_ids & set(domains)
    if present_split_state_domain_ids == split_state_domain_ids:
        product_domain_ids = OBSERVER_GRANT_REQUEST_SPLIT_PRODUCT_DOMAINS
        start_product = OBSERVER_GRANT_REQUEST_SPLIT_START_PRODUCT
        domain_mode = (
            "SPLIT_OUTER_LIFECYCLE_AND_LOCAL_GRANT_STATE"
            if "ROOT" not in domains
            else "SPLIT_WITH_LEGACY_ROOT_STILL_PRESENT"
        )
    else:
        require(
            not present_split_state_domain_ids,
            (
                "OBSERVER_ADMISSION: partial split request-product "
                f"domains {sorted(present_split_state_domain_ids)}"
            ),
        )
        product_domain_ids = (
            "ROOT",
            "OBSERVER_GRANT_REQUEST_OPERATION_STATE",
        )
        start_product = OBSERVER_GRANT_REQUEST_START_PRODUCT
        domain_mode = "LEGACY_CONFLATED_ROOT"

    require(
        set(product_domain_ids).issubset(domains),
        (
            "OBSERVER_ADMISSION: missing request-product state domains "
            f"{sorted(set(product_domain_ids) - set(domains))}"
        ),
    )
    return {
        "domain_mode": domain_mode,
        "domains": domains,
        "product_domain_ids": product_domain_ids,
        "selector": selector,
        "start_product": start_product,
    }


def _observer_grant_request_case_causal_edges(
    *,
    event_id: str,
    evidence_variant_id: str,
    resolution_cause: str | None = None,
) -> frozenset[tuple[str, str]]:
    """Return monotonic verified-source-outcome edges for one modeled case."""

    if event_id in OBSERVER_GRANT_REQUEST_INSTALL_EVENTS:
        return frozenset(
            {
                (
                    OBSERVER_GRANT_REQUEST_INITIAL_CAUSAL_STATE,
                    "LIVE_RESPONSE",
                ),
                ("LIVE_RESPONSE", "LIVE_RESPONSE"),
            }
        )
    if event_id == OBSERVER_GRANT_REQUEST_TERMINAL_OBSERVATION_EVENT:
        return frozenset(
            {
                (
                    "ACCEPTED_TERMINAL_PENDING_AGGREGATES",
                    "ACCEPTED_TERMINAL_PENDING_AGGREGATES",
                ),
                (
                    "LIVE_RESPONSE",
                    "ACCEPTED_TERMINAL_PENDING_AGGREGATES",
                ),
                (
                    OBSERVER_GRANT_REQUEST_INITIAL_CAUSAL_STATE,
                    "ACCEPTED_TERMINAL_PENDING_AGGREGATES",
                ),
            }
        )
    if event_id in OBSERVER_GRANT_REQUEST_UNUSED_RESOLUTION_EVENTS:
        cause = resolution_cause
        if cause in OBSERVER_GRANT_REQUEST_TERMINAL_RESOLUTION_CAUSES:
            if event_id == OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT and cause == (
                "ACCEPTED_GRANT_FULLY_CLOSED_WITHOUT_LOCAL_INSTALLATION"
            ):
                return frozenset()
            causal_state = OBSERVER_GRANT_REQUEST_RESOLUTION_CAUSE_STATE[cause]
            edges = {(causal_state, causal_state)}
            if causal_state in {
                "SERVER_SLOT_CANCELED_UNUSED",
                "SERVER_SLOT_EXPIRED_UNUSED",
            }:
                edges.add(
                    (
                        OBSERVER_GRANT_REQUEST_INITIAL_CAUSAL_STATE,
                        causal_state,
                    )
                )
            return frozenset(edges)
        return frozenset()
    return frozenset(
        {(scenario, scenario) for scenario in OBSERVER_GRANT_REQUEST_CAUSAL_STATES}
    )


def _observer_grant_request_variant_exact_value(
    *,
    event: dict[str, Any],
    evidence_variant_id: str,
    field: str,
    allowed_values: frozenset[str],
) -> str | None:
    """Return one verifier-derived closed-union value for a variant."""

    variant = next(
        (
            item
            for item in event["decision_model"]["evidence_variant_definitions"]
            if item["evidence_variant_id"] == evidence_variant_id
        ),
        None,
    )
    if variant is None:
        return None
    derived_values = {
        condition["value"]
        for condition in variant["truth_conditions"]
        if condition["field"] == field
        and condition["operator"] == "EQUALS"
        and condition["value"] in allowed_values
    }
    if len(derived_values) != 1:
        return None
    return next(iter(derived_values))


def _observer_grant_request_case_resolution_cause(
    *,
    event: dict[str, Any],
    evidence_variant_id: str,
) -> str | None:
    """Derive an exact terminal cause rather than trusting a variant label."""

    event_id = event["event_id"]
    if event_id not in OBSERVER_GRANT_REQUEST_UNUSED_RESOLUTION_EVENTS:
        return None
    cause_field = (
        OBSERVER_GRANT_REQUEST_INTENT_CAUSE_FIELD
        if event_id == OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT
        else OBSERVER_GRANT_REQUEST_CAUSE_FIELD
    )
    return _observer_grant_request_variant_exact_value(
        event=event,
        evidence_variant_id=evidence_variant_id,
        field=cause_field,
        allowed_values=OBSERVER_GRANT_REQUEST_TERMINAL_RESOLUTION_CAUSES,
    )


def _observer_grant_request_case_kind_scope(
    *,
    event: dict[str, Any],
    evidence_variant_id: str,
) -> frozenset[str]:
    """Derive one request kind for a shared event from verifier truth."""

    event_id = event["event_id"]
    static_scope = OBSERVER_GRANT_REQUEST_EVENT_KIND_SCOPE.get(
        event_id,
        OBSERVER_GRANT_REQUEST_KINDS,
    )
    if event_id not in OBSERVER_GRANT_REQUEST_SHARED_KIND_EVENTS:
        return static_scope
    derived_kind = _observer_grant_request_variant_exact_value(
        event=event,
        evidence_variant_id=evidence_variant_id,
        field=OBSERVER_GRANT_REQUEST_KIND_FIELD,
        allowed_values=OBSERVER_GRANT_REQUEST_KINDS,
    )
    if derived_kind is None or derived_kind not in static_scope:
        return frozenset()
    return frozenset({derived_kind})


def _expected_request_kind_product_resolution_rows() -> set[
    tuple[str, str, str, str, str, str]
]:
    """Return the closed permanent-intent branch/kind/local-state product."""

    rows: set[tuple[str, str, str, str, str, str]] = set()
    local_contract = {
        "ATTACH": (
            "PENDING_FIRST_ATTACH",
            "PENDING_FIRST_ATTACH",
            "TYPED_INAPPLICABLE",
        ),
        "REATTACH": (
            "TERMINAL",
            "TERMINAL",
            "TYPED_INAPPLICABLE",
        ),
        "RENEW": (
            "TERMINAL",
            "TERMINAL",
            "EXACT_G0_CLOSURE_REQUIRED",
        ),
    }
    for (
        branch_id,
        causal_outcome,
    ) in OBSERVER_GRANT_PERMANENT_RESOLUTION_CAUSE_BY_PARTITION_BRANCH.items():
        for request_kind, (
            from_local_state,
            to_local_state,
            g0_closure_requirement,
        ) in local_contract.items():
            rows.add(
                (
                    branch_id,
                    causal_outcome,
                    from_local_state,
                    g0_closure_requirement,
                    request_kind,
                    to_local_state,
                )
            )
    return rows


def _validate_request_kind_product_partition_contract(
    *,
    event: dict[str, Any],
    partition: dict[str, Any],
) -> list[dict[str, str]]:
    """Validate and return exact kind-refined bulk resolution rows."""

    event_id = event["event_id"]
    require_exact(
        event_id,
        OBSERVER_GRANT_SOURCE_NAMESPACE_CLOSURE_IMPORT_EVENT,
        "request-kind operation partition owner event",
    )
    require_exact(
        partition["partition_id"],
        "P002",
        f"{event_id} request-operation partition identity",
    )
    require_exact(
        partition["state_domain"],
        "OBSERVER_GRANT_REQUEST_OPERATION_STATE",
        f"{event_id}.P002 state domain",
    )
    contract = partition.get("request_kind_product_contract")
    require(
        contract is not None,
        f"{event_id}.P002: missing request_kind_product_contract",
    )
    expected_metadata = {
        "causal_outcome_source": (
            "VERIFIER_DERIVED_FROM_BRANCH_EXACT_PROOF_NOT_CALLER_LABEL"
        ),
        "kind_field": OBSERVER_GRANT_REQUEST_KIND_FIELD,
        "kind_source": "VERIFIED_RETAINED_OPERATION_STABLE_KEY",
        "operation_edge_source": "EXACT_PARTITION_BRANCH_FROM_AND_TO_STATE",
        "outer_state_rule": "PRESERVE_EXACT_INSTALLED_OUTER_STATE",
        "unknown_missing_duplicate_or_cross_kind": "REJECT_WITHOUT_STATE_CHANGE",
    }
    for field, expected in expected_metadata.items():
        require_exact(
            contract[field],
            expected,
            f"{event_id}.P002 request-kind product {field}",
        )

    rows = contract["resolution_rows"]
    require_unique(
        rows,
        f"{event_id}.P002 request-kind product resolution rows",
    )
    actual_rows = {
        (
            row["branch_id"],
            row["causal_outcome"],
            row["from_local_state"],
            row["g0_closure_requirement"],
            row["request_kind"],
            row["to_local_state"],
        )
        for row in rows
    }
    require_exact(
        actual_rows,
        _expected_request_kind_product_resolution_rows(),
        f"{event_id}.P002 request-kind product resolution row union",
    )

    branch_ids = [branch["branch_id"] for branch in partition["branches"]]
    require_unique(
        branch_ids,
        f"{event_id}.P002 partition branch identities",
    )
    branch_by_id = {branch["branch_id"]: branch for branch in partition["branches"]}
    require_exact(
        set(branch_by_id),
        set(OBSERVER_GRANT_PERMANENT_RESOLUTION_CAUSE_BY_PARTITION_BRANCH)
        | set(OBSERVER_GRANT_REQUEST_IMPORT_PRESERVE_BRANCH_STATES),
        f"{event_id}.P002 closed partition branch union",
    )
    for branch_id in OBSERVER_GRANT_PERMANENT_RESOLUTION_CAUSE_BY_PARTITION_BRANCH:
        branch = branch_by_id.get(branch_id)
        require(
            branch is not None,
            f"{event_id}.P002: missing resolving branch {branch_id}",
        )
        require_exact(
            (branch["from_state"], branch["to_state"]),
            ("INTENT_PREPARED", "RESOLVED_WITHOUT_INSTALLATION"),
            f"{event_id}.P002.{branch_id} operation edge",
        )

    preserve_branch_ids = set(OBSERVER_GRANT_REQUEST_IMPORT_PRESERVE_BRANCH_STATES)
    preserve_scopes = contract["preserve_branch_kind_scopes"]
    require_unique(
        preserve_scopes,
        f"{event_id}.P002 preserve-branch kind scopes",
    )
    actual_preserve_scopes = {
        (scope["branch_id"], tuple(scope["request_kinds"])) for scope in preserve_scopes
    }
    expected_preserve_scopes = {
        (branch_id, tuple(sorted(OBSERVER_GRANT_REQUEST_KINDS)))
        for branch_id in preserve_branch_ids
    }
    require_exact(
        actual_preserve_scopes,
        expected_preserve_scopes,
        f"{event_id}.P002 preserve-branch kind-scope union",
    )
    for (
        branch_id,
        expected_state,
    ) in OBSERVER_GRANT_REQUEST_IMPORT_PRESERVE_BRANCH_STATES.items():
        branch = branch_by_id[branch_id]
        require_exact(
            (branch["from_state"], branch["to_state"]),
            (expected_state, expected_state),
            f"{event_id}.P002.{branch_id} preserve edge",
        )
    return rows


def _request_product_finalization_guard_states(
    event: dict[str, Any],
) -> set[str] | None:
    """Validate the one complete operation-partition finalization guard."""

    guard = event.get("request_product_finalization_guard")
    if event["event_id"] != OBSERVER_GRANT_REQUEST_FINALIZATION_EVENT:
        require(
            guard is None,
            (
                f"OBSERVER_ADMISSION.{event['event_id']}: request-product "
                "finalization guard is owned only by "
                f"{OBSERVER_GRANT_REQUEST_FINALIZATION_EVENT}"
            ),
        )
        return None
    require(
        guard is not None,
        (
            f"OBSERVER_ADMISSION.{OBSERVER_GRANT_REQUEST_FINALIZATION_EVENT}: "
            "missing request_product_finalization_guard"
        ),
    )
    expected = {
        "coverage": "EXACT_DISJOINT_COMPLETE_OPERATION_KEY_PARTITION",
        "operation_state_domain": "OBSERVER_GRANT_REQUEST_OPERATION_STATE",
        "preservation": "BYTE_IDENTICAL_EVERY_OPERATION_ENTRY",
        "required_exact_states": sorted(
            OBSERVER_GRANT_REQUEST_TERMINAL_OPERATION_STATES
        ),
        "unknown_missing_duplicate_or_nonterminal": "REJECT_WITHOUT_STATE_CHANGE",
    }
    require_exact(
        guard,
        expected,
        (
            f"OBSERVER_ADMISSION.{OBSERVER_GRANT_REQUEST_FINALIZATION_EVENT} "
            "request-product finalization guard"
        ),
    )
    require_exact(
        event["operation_scope"],
        "BOUNDED_KEY_SET",
        (
            f"OBSERVER_ADMISSION.{OBSERVER_GRANT_REQUEST_FINALIZATION_EVENT} "
            "operation scope"
        ),
    )
    require(
        "EVERY_REQUEST_OPERATION_HAS_EXACTLY_ONE_TERMINAL_RESOLUTION"
        in event["pre_cas_content"]["required_bindings"],
        (
            f"OBSERVER_ADMISSION.{OBSERVER_GRANT_REQUEST_FINALIZATION_EVENT}: "
            "guard is not bound by the pre-CAS fact"
        ),
    )
    return set(guard["required_exact_states"])


def _validate_request_product_finalization_partition_contract(
    *,
    event: dict[str, Any],
    partition: dict[str, Any],
    operation_key_type: str,
    required_states: set[str],
) -> None:
    """Validate the complete read/compare/preserve operation partition."""

    event_label = f"OBSERVER_ADMISSION.{OBSERVER_GRANT_REQUEST_FINALIZATION_EVENT}"
    require_exact(
        event["event_id"],
        OBSERVER_GRANT_REQUEST_FINALIZATION_EVENT,
        "request-product finalization partition owner event",
    )
    require_exact(
        partition["partition_id"],
        "P001",
        f"{event_label} operation partition identity",
    )
    require_exact(
        partition["key_type"],
        operation_key_type,
        f"{event_label} operation partition key type",
    )
    require_exact(
        partition["coverage"],
        "EXACT_DISJOINT_COMPLETE_OPERATION_KEY_PARTITION",
        f"{event_label} operation partition coverage",
    )
    require_exact(
        partition["bijection"],
        "EXACTLY_ONE_BRANCH_AND_OUTCOME_PER_OPERATION_KEY",
        f"{event_label} operation partition bijection",
    )
    require_exact(
        partition["empty_partitions"],
        "PERMITTED_AND_EXPLICIT",
        f"{event_label} operation partition empty-partition rule",
    )
    require_exact(
        partition["inventory_semantics"],
        "EXACT_COMPLETE_MANIFEST_BOUNDED_REQUEST_OPERATION_KEY_UNIVERSE",
        f"{event_label} operation partition inventory",
    )
    require_exact(
        partition["missing_extra_duplicate_or_nonterminal"],
        "REJECT_WITHOUT_STATE_CHANGE",
        f"{event_label} operation partition rejection rule",
    )
    require_exact(
        partition["preserve_unlisted_keys"],
        True,
        f"{event_label} operation partition sibling preservation",
    )
    require_exact(
        set(partition["applies_to_semantic_case_ids"]),
        {case["semantic_case_id"] for case in event["transition_cases"]},
        f"{event_label} operation partition case coverage",
    )
    expected_key_partitions = {
        "ABSENT": "CANONICAL_COMPLETE_UNUSED_REQUEST_OPERATION_KEY_SET",
        "INSTALLED": "CANONICAL_COMPLETE_INSTALLED_REQUEST_OPERATION_KEY_SET",
        "RESOLVED_WITHOUT_INSTALLATION": (
            "CANONICAL_COMPLETE_RESOLVED_WITHOUT_INSTALLATION_REQUEST_OPERATION_KEY_SET"
        ),
    }
    require_exact(
        required_states,
        set(expected_key_partitions),
        f"{event_label} operation partition state union",
    )
    branches = partition["branches"]
    require_unique(
        [branch["branch_id"] for branch in branches],
        f"{event_label} operation partition branch identities",
    )
    actual_branches = {
        branch["from_state"]: {
            "branch_id": branch["branch_id"],
            "cardinality": branch["cardinality"],
            "entry_effect": branch["entry_effect"],
            "from_state": branch["from_state"],
            "key_mode": branch["key_mode"],
            "key_partition": branch["key_partition"],
            "key_ref": branch["key_ref"],
            "to_state": branch["to_state"],
            "version_effect": branch["version_effect"],
        }
        for branch in branches
    }
    expected_branches = {
        state: {
            "branch_id": f"{state}_PRESERVED",
            "cardinality": "ZERO_OR_MORE_BOUNDED_KEYS",
            "entry_effect": "PRESERVE_VALIDATE_ONLY",
            "from_state": state,
            "key_mode": "PARTITION",
            "key_partition": expected_key_partitions[state],
            "key_ref": operation_key_type,
            "to_state": state,
            "version_effect": "UNCHANGED",
        }
        for state in sorted(required_states)
    }
    require_exact(
        actual_branches,
        expected_branches,
        f"{event_label} operation partition branches",
    )


def _request_product_terminal_contract(
    data: dict[str, Any],
) -> dict[str, Any]:
    """Validate the exact contextual terminal predicate and causal closure."""

    contract = data["observer_grant_request_target_profile"].get(
        "request_product_terminal_contract"
    )
    require(
        contract is not None,
        (
            "observer_grant_request_target_profile: missing "
            "request_product_terminal_contract"
        ),
    )
    resolved_causal_states = {
        "ACCEPTED_TERMINAL_PENDING_AGGREGATES",
        "SERVER_SLOT_CANCELED_UNUSED",
        "SERVER_SLOT_EXPIRED_UNUSED",
        *OBSERVER_GRANT_PREPARED_INTENT_PERMANENT_RESOLUTION_CAUSES,
    }
    expected = {
        "causal_states_by_operation_state": {
            "ABSENT": [OBSERVER_GRANT_REQUEST_INITIAL_CAUSAL_STATE],
            "INSTALLED": ["LIVE_RESPONSE"],
            "RESOLVED_WITHOUT_INSTALLATION": sorted(resolved_causal_states),
        },
        "local_state": "TERMINAL",
        "operation_states": sorted(OBSERVER_GRANT_REQUEST_TERMINAL_OPERATION_STATES),
        "outer_state": "TERMINAL",
        "predicate": "EXACT_CONTEXTUAL_PRODUCT_TERMINAL_SET",
        "unknown_default_or_mismatch": "NOT_TERMINAL",
    }
    require_exact(
        contract,
        expected,
        "observer request-product contextual terminal contract",
    )
    return contract


def _observer_grant_request_product_graph(
    data: dict[str, Any],
) -> dict[str, Any]:
    """Build kind- and source-outcome-refined one-key transition graphs."""

    context = _observer_grant_request_product_context(data)
    selector = context["selector"]
    domains = context["domains"]
    product_domain_ids = context["product_domain_ids"]
    operation_domain_id = "OBSERVER_GRANT_REQUEST_OPERATION_STATE"
    edge_by_id = {edge["edge_id"]: edge for edge in selector["state_edge_catalog"]}
    terminal_contract = _request_product_terminal_contract(data)
    event_by_id = {event["event_id"]: event for event in selector["events"]}
    for required_event_id in (
        OBSERVER_GRANT_REQUEST_FINALIZATION_EVENT,
        OBSERVER_GRANT_SOURCE_NAMESPACE_CLOSURE_IMPORT_EVENT,
    ):
        require(
            required_event_id in event_by_id,
            f"OBSERVER_ADMISSION: missing {required_event_id}",
        )

    operation_event_ids = {
        event["event_id"]
        for event in selector["events"]
        if any(
            edge_by_id[edge_ref]["state_domain"] == operation_domain_id
            for transition_case in event["transition_cases"]
            for edge_ref in transition_case["state_edge_refs"]
        )
        or any(
            partition["state_domain"] == operation_domain_id
            for partition in event["partition_effects"]
        )
    }
    unknown_operation_event_ids = operation_event_ids - set(
        OBSERVER_GRANT_REQUEST_EVENT_KIND_SCOPE
    )
    require(
        not unknown_operation_event_ids,
        (
            "OBSERVER_ADMISSION: request-operation events lack an exact "
            f"kind scope: {sorted(unknown_operation_event_ids)}"
        ),
    )

    causal_scenarios = OBSERVER_GRANT_REQUEST_CAUSAL_STATES
    transitions_by_kind: dict[
        str,
        set[tuple[tuple[str, ...], tuple[str, ...]]],
    ] = {kind: set() for kind in OBSERVER_GRANT_REQUEST_KINDS}
    causal_transitions_by_kind: dict[
        str,
        set[tuple[tuple[str, ...], tuple[str, ...]]],
    ] = {kind: set() for kind in OBSERVER_GRANT_REQUEST_KINDS}
    unclassified_sensitive_variants: set[tuple[str, str]] = set()
    unclassified_kind_variants: set[tuple[str, str]] = set()
    product_domain_id_set = set(product_domain_ids)
    for event in selector["events"]:
        event_id = event["event_id"]
        finalization_guard_states = _request_product_finalization_guard_states(event)
        request_operation_partitions = []
        finalization_partition_count = 0
        for partition in event["partition_effects"]:
            if partition["state_domain"] not in product_domain_id_set:
                continue
            require_exact(
                partition["state_domain"],
                operation_domain_id,
                (
                    f"OBSERVER_ADMISSION.{event_id} request-product "
                    "partition state domain"
                ),
            )
            if finalization_guard_states is not None:
                _validate_request_product_finalization_partition_contract(
                    event=event,
                    partition=partition,
                    operation_key_type=domains[operation_domain_id]["key_type"],
                    required_states=finalization_guard_states,
                )
                finalization_partition_count += 1
                continue
            resolution_rows = _validate_request_kind_product_partition_contract(
                event=event,
                partition=partition,
            )
            request_operation_partitions.append((partition, resolution_rows))
        if finalization_guard_states is not None:
            require_exact(
                finalization_partition_count,
                1,
                (
                    f"OBSERVER_ADMISSION.{event_id} request-product "
                    "finalization partition count"
                ),
            )
        for transition_case in event["transition_cases"]:
            event_kind_scope = _observer_grant_request_case_kind_scope(
                event=event,
                evidence_variant_id=transition_case["evidence_variant_id"],
            )
            if (
                event_id in OBSERVER_GRANT_REQUEST_SHARED_KIND_EVENTS
                and not event_kind_scope
            ):
                unclassified_kind_variants.add(
                    (
                        event_id,
                        transition_case["evidence_variant_id"],
                    )
                )
            relevant_edges: dict[str, list[dict[str, Any]]] = {
                domain_id: [] for domain_id in product_domain_ids
            }
            for edge_ref in transition_case["state_edge_refs"]:
                edge = edge_by_id[edge_ref]
                if edge["state_domain"] in product_domain_id_set:
                    relevant_edges[edge["state_domain"]].append(edge)
            if not any(relevant_edges.values()):
                continue
            if (
                finalization_guard_states is not None
                and relevant_edges[operation_domain_id]
            ):
                fail(
                    f"OBSERVER_ADMISSION.{event_id}."
                    f"{transition_case['semantic_case_id']}: finalization "
                    "must preserve operation entries through the complete "
                    "partition, not a scalar edge"
                )
            for domain_id, edges in relevant_edges.items():
                require(
                    len(edges) <= 1,
                    (
                        f"OBSERVER_ADMISSION.{event_id}."
                        f"{transition_case['semantic_case_id']}: multiple "
                        f"{domain_id} edges cannot prove one-key product closure"
                    ),
                )

            compatible_causal_edges = _observer_grant_request_case_causal_edges(
                event_id=event_id,
                evidence_variant_id=transition_case["evidence_variant_id"],
                resolution_cause=(
                    _observer_grant_request_case_resolution_cause(
                        event=event,
                        evidence_variant_id=transition_case["evidence_variant_id"],
                    )
                ),
            )
            if (
                event_id in OBSERVER_GRANT_REQUEST_UNUSED_RESOLUTION_EVENTS
                and not compatible_causal_edges
            ):
                unclassified_sensitive_variants.add(
                    (
                        event_id,
                        transition_case["evidence_variant_id"],
                    )
                )

            source_state_sets: list[set[str]] = []
            target_state_by_domain: list[str | None] = []
            for domain_id in product_domain_ids:
                edges = relevant_edges[domain_id]
                if edges:
                    source_state_sets.append({edges[0]["from_state"]})
                    target_state_by_domain.append(edges[0]["to_state"])
                elif (
                    domain_id == operation_domain_id
                    and finalization_guard_states is not None
                ):
                    source_state_sets.append(finalization_guard_states)
                    target_state_by_domain.append(None)
                else:
                    source_state_sets.append(set(domains[domain_id]["states"]))
                    target_state_by_domain.append(None)

            for source_state in product(*source_state_sets):
                target_state = tuple(
                    target if target is not None else source
                    for source, target in zip(
                        source_state,
                        target_state_by_domain,
                        strict=True,
                    )
                )
                transition = (source_state, target_state)
                for kind in event_kind_scope:
                    transitions_by_kind[kind].add(transition)
                    for (
                        source_causal_scenario,
                        target_causal_scenario,
                    ) in compatible_causal_edges:
                        causal_transitions_by_kind[kind].add(
                            (
                                (
                                    *source_state,
                                    source_causal_scenario,
                                ),
                                (
                                    *target_state,
                                    target_causal_scenario,
                                ),
                            )
                        )

        for partition, resolution_rows in request_operation_partitions:
            branch_by_id = {
                branch["branch_id"]: branch for branch in partition["branches"]
            }
            applicable_case_ids = set(partition["applies_to_semantic_case_ids"])
            evidence_variant_ids = {
                variant["evidence_variant_id"]
                for variant in event["decision_model"]["evidence_variant_definitions"]
            }
            for row in resolution_rows:
                branch = branch_by_id[row["branch_id"]]
                matching_cases: list[
                    tuple[dict[str, Any], dict[str, Any], dict[str, Any]]
                ] = []
                for transition_case in event["transition_cases"]:
                    if transition_case["semantic_case_id"] not in applicable_case_ids:
                        continue
                    case_edges = [
                        edge_by_id[edge_ref]
                        for edge_ref in transition_case["state_edge_refs"]
                    ]
                    outer_edges = [
                        edge
                        for edge in case_edges
                        if edge["state_domain"] == "OUTER_LIFECYCLE"
                    ]
                    local_edges = [
                        edge
                        for edge in case_edges
                        if edge["state_domain"] == "LOCAL_GRANT_STATE"
                    ]
                    operation_edges = [
                        edge
                        for edge in case_edges
                        if edge["state_domain"] == operation_domain_id
                    ]
                    require(
                        not operation_edges,
                        (
                            f"OBSERVER_ADMISSION.{event_id}."
                            f"{transition_case['semantic_case_id']}: bulk "
                            "operation partition cannot also carry a scalar "
                            "request-operation edge"
                        ),
                    )
                    if (
                        len(outer_edges) == 1
                        and len(local_edges) == 1
                        and (
                            local_edges[0]["from_state"],
                            local_edges[0]["to_state"],
                        )
                        == (
                            row["from_local_state"],
                            row["to_local_state"],
                        )
                    ):
                        matching_cases.append(
                            (transition_case, outer_edges[0], local_edges[0])
                        )
                require(
                    matching_cases,
                    (
                        f"OBSERVER_ADMISSION.{event_id}.{partition['partition_id']}."
                        f"{row['branch_id']}.{row['request_kind']}: no "
                        "matching outer/local transition case"
                    ),
                )
                actual_outer_variant_coverage = {
                    (
                        outer_edge["from_state"],
                        transition_case["evidence_variant_id"],
                    )
                    for transition_case, outer_edge, _ in matching_cases
                    if outer_edge["from_state"] == outer_edge["to_state"]
                }
                expected_outer_variant_coverage = {
                    (outer_state, evidence_variant_id)
                    for outer_state in domains["OUTER_LIFECYCLE"]["states"]
                    for evidence_variant_id in evidence_variant_ids
                }
                require_exact(
                    actual_outer_variant_coverage,
                    expected_outer_variant_coverage,
                    (
                        f"OBSERVER_ADMISSION.{event_id}."
                        f"{partition['partition_id']}.{row['branch_id']}."
                        f"{row['request_kind']} outer/evidence coverage"
                    ),
                )
                for _, outer_edge, local_edge in matching_cases:
                    source_state = (
                        outer_edge["from_state"],
                        local_edge["from_state"],
                        branch["from_state"],
                    )
                    target_state = (
                        outer_edge["to_state"],
                        local_edge["to_state"],
                        branch["to_state"],
                    )
                    request_kind = row["request_kind"]
                    transitions_by_kind[request_kind].add((source_state, target_state))
                    causal_transitions_by_kind[request_kind].add(
                        (
                            (
                                *source_state,
                                OBSERVER_GRANT_REQUEST_INITIAL_CAUSAL_STATE,
                            ),
                            (
                                *target_state,
                                row["causal_outcome"],
                            ),
                        )
                    )

    require_exact(
        tuple(product_domain_ids),
        OBSERVER_GRANT_REQUEST_SPLIT_PRODUCT_DOMAINS,
        "observer request-product contextual terminal domain order",
    )
    terminal_products = {
        (
            terminal_contract["outer_state"],
            terminal_contract["local_state"],
            operation_state,
        )
        for operation_state in terminal_contract["operation_states"]
    }
    causal_terminal_products = {
        (
            terminal_contract["outer_state"],
            terminal_contract["local_state"],
            operation_state,
            causal_state,
        )
        for operation_state, causal_states in terminal_contract[
            "causal_states_by_operation_state"
        ].items()
        for causal_state in causal_states
    }
    return {
        **context,
        "causal_scenarios": causal_scenarios,
        "causal_terminal_products": causal_terminal_products,
        "causal_transitions_by_kind": causal_transitions_by_kind,
        "missing_operation_event_ids": sorted(
            set(OBSERVER_GRANT_REQUEST_EVENT_KIND_SCOPE) - operation_event_ids
        ),
        "operation_event_ids": operation_event_ids,
        "terminal_products": terminal_products,
        "transitions_by_kind": transitions_by_kind,
        "unclassified_sensitive_variants": [
            {
                "event_id": event_id,
                "evidence_variant_id": evidence_variant_id,
            }
            for event_id, evidence_variant_id in sorted(unclassified_sensitive_variants)
        ],
        "unclassified_kind_variants": [
            {
                "event_id": event_id,
                "evidence_variant_id": evidence_variant_id,
            }
            for event_id, evidence_variant_id in sorted(unclassified_kind_variants)
        ],
    }


def _observer_grant_request_product_liveness_rows(
    data: dict[str, Any],
) -> list[str]:
    """Check one exact request key without conflating operation kinds."""

    graph = _observer_grant_request_product_graph(data)
    rows: list[str] = []
    for kind in sorted(OBSERVER_GRANT_REQUEST_KINDS):
        initial_state = graph["start_product"][kind]
        require(
            all(
                state in graph["domains"][domain_id]["states"]
                for domain_id, state in zip(
                    graph["product_domain_ids"],
                    initial_state,
                    strict=True,
                )
            ),
            (
                f"OBSERVER_ADMISSION {kind}: unknown request-product "
                f"start state {initial_state!r}"
            ),
        )
        missing = _product_states_without_terminal_path(
            initial_state=initial_state,
            transitions=graph["transitions_by_kind"][kind],
            terminal_states=graph["terminal_products"],
        )
        rows.extend(
            ".".join(
                [
                    kind,
                    *(
                        f"{domain_id}={state}"
                        for domain_id, state in zip(
                            graph["product_domain_ids"],
                            product_state,
                            strict=True,
                        )
                    ),
                ]
            )
            for product_state in sorted(missing)
        )
    return rows


def _observer_grant_request_causal_transition_contract_issues(
    selector: dict[str, Any],
) -> list[str]:
    """Check the operation-phase polarity of cause-sensitive events."""

    operation_domain_id = "OBSERVER_GRANT_REQUEST_OPERATION_STATE"
    edge_by_id = {edge["edge_id"]: edge for edge in selector["state_edge_catalog"]}
    event_by_id = {event["event_id"]: event for event in selector["events"]}
    issues: list[str] = []

    def operation_pairs_by_variant(
        event_id: str,
    ) -> dict[str, set[tuple[str, str]]]:
        event = event_by_id.get(event_id)
        if event is None:
            issues.append(f"{event_id}:MISSING_EVENT")
            return {}
        result: dict[str, set[tuple[str, str]]] = {}
        for transition_case in event["transition_cases"]:
            operation_edges = [
                edge_by_id[edge_ref]
                for edge_ref in transition_case["state_edge_refs"]
                if edge_by_id[edge_ref]["state_domain"] == operation_domain_id
            ]
            if len(operation_edges) != 1:
                issues.append(
                    f"{event_id}."
                    f"{transition_case['semantic_case_id']}:"
                    "REQUIRES_EXACTLY_ONE_EXPLICIT_OPERATION_EDGE"
                )
                continue
            edge = operation_edges[0]
            variant_key = transition_case["evidence_variant_id"]
            if event_id in OBSERVER_GRANT_REQUEST_UNUSED_RESOLUTION_EVENTS:
                derived_cause = _observer_grant_request_case_resolution_cause(
                    event=event,
                    evidence_variant_id=variant_key,
                )
                if derived_cause is not None:
                    variant_key = derived_cause
            result.setdefault(
                variant_key,
                set(),
            ).add((edge["from_state"], edge["to_state"]))
        return result

    exact_lifecycle_pairs = {
        OBSERVER_GRANT_REQUEST_PREPARE_EVENT: {("ABSENT", "INTENT_PREPARED")},
        OBSERVER_GRANT_REQUEST_AMBIGUITY_EVENT: {
            (
                "PENDING_RESPONSE",
                "AMBIGUOUS_SERVER_ACCEPTANCE",
            )
        },
        **{
            event_id: {("INTENT_PREPARED", "PENDING_RESPONSE")}
            for event_id in OBSERVER_GRANT_REQUEST_BEGIN_EVENTS
        },
    }
    for event_id, expected_pairs in exact_lifecycle_pairs.items():
        pairs_by_variant = operation_pairs_by_variant(event_id)
        actual_pairs = (
            set().union(*pairs_by_variant.values()) if pairs_by_variant else set()
        )
        if actual_pairs != expected_pairs:
            issues.append(
                f"{event_id}:OPERATION_EDGE_SET_MUST_EQUAL_"
                f"{sorted(expected_pairs)!r}_"
                f"ACTUAL_{sorted(actual_pairs)!r}"
            )

    intent_resolution_pairs_by_variant = operation_pairs_by_variant(
        OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT
    )
    expected_intent_resolution_pairs = {
        ("INTENT_PREPARED", "RESOLVED_WITHOUT_INSTALLATION")
    }
    for cause in sorted(
        {
            "SERVER_SLOT_CANCELED_UNUSED",
            "SERVER_SLOT_EXPIRED_UNUSED",
        }
    ):
        actual_pairs = intent_resolution_pairs_by_variant.get(
            cause,
            set(),
        )
        if actual_pairs != expected_intent_resolution_pairs:
            issues.append(
                f"{OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT}."
                f"{cause}:OPERATION_EDGE_SET_MUST_EQUAL_"
                f"{sorted(expected_intent_resolution_pairs)!r}_"
                f"ACTUAL_{sorted(actual_pairs)!r}"
            )

    observation_pairs_by_variant = operation_pairs_by_variant(
        OBSERVER_GRANT_REQUEST_TERMINAL_OBSERVATION_EVENT
    )
    observation_pairs = (
        set().union(*observation_pairs_by_variant.values())
        if observation_pairs_by_variant
        else set()
    )
    required_observation_pairs = {
        (
            "AMBIGUOUS_SERVER_ACCEPTANCE",
            "TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE",
        ),
        (
            "PENDING_RESPONSE",
            "TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE",
        ),
        (
            "TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE",
            "TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE",
        ),
    }
    if (
        OBSERVER_GRANT_REQUEST_TERMINAL_OBSERVATION_EVENT in event_by_id
        and observation_pairs != required_observation_pairs
    ):
        issues.append(
            f"{OBSERVER_GRANT_REQUEST_TERMINAL_OBSERVATION_EVENT}:"
            "OPERATION_EDGE_SET_MUST_EQUAL_"
            f"{sorted(required_observation_pairs)!r}_"
            f"ACTUAL_{sorted(observation_pairs)!r}"
        )

    for event_id in sorted(OBSERVER_GRANT_REQUEST_INSTALL_EVENTS):
        install_pairs_by_variant = operation_pairs_by_variant(event_id)
        install_pairs = (
            set().union(*install_pairs_by_variant.values())
            if install_pairs_by_variant
            else set()
        )
        expected_install_pairs = {("PENDING_RESPONSE", "INSTALLED")}
        if install_pairs != expected_install_pairs:
            issues.append(
                f"{event_id}:OPERATION_EDGE_SET_MUST_EQUAL_"
                f"{sorted(expected_install_pairs)!r}_"
                f"ACTUAL_{sorted(install_pairs)!r}"
            )

    expected_unused_pairs = {
        (
            "AMBIGUOUS_SERVER_ACCEPTANCE",
            "RESOLVED_WITHOUT_INSTALLATION",
        ),
        ("PENDING_RESPONSE", "RESOLVED_WITHOUT_INSTALLATION"),
    }
    expected_accepted_pairs = {
        (
            "TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE",
            "RESOLVED_WITHOUT_INSTALLATION",
        )
    }
    for event_id in sorted(OBSERVER_GRANT_REQUEST_RESOLVER_EVENTS):
        pairs_by_variant = operation_pairs_by_variant(event_id)
        for cause in sorted(OBSERVER_GRANT_REQUEST_TERMINAL_RESOLUTION_CAUSES):
            actual_pairs = pairs_by_variant.get(cause, set())
            expected_pairs = (
                expected_accepted_pairs
                if cause == ("ACCEPTED_GRANT_FULLY_CLOSED_WITHOUT_LOCAL_INSTALLATION")
                else expected_unused_pairs
            )
            if actual_pairs != expected_pairs:
                issues.append(
                    f"{event_id}.{cause}:OPERATION_EDGE_SET_MUST_EQUAL_"
                    f"{sorted(expected_pairs)!r}_"
                    f"ACTUAL_{sorted(actual_pairs)!r}"
                )
    return sorted(issues)


def _observer_grant_request_successor_contract_issues(
    selector: dict[str, Any],
) -> list[str]:
    """Check kind, cause, outer phase, and local successor polarity."""

    required_domains = set(OBSERVER_GRANT_REQUEST_SPLIT_PRODUCT_DOMAINS)
    actual_domains = {domain["state_domain"] for domain in selector["state_domains"]}
    if not required_domains.issubset(actual_domains):
        return [
            (
                "SPLIT_REQUEST_SUCCESSOR_DOMAINS_MISSING:"
                f"{sorted(required_domains - actual_domains)}"
            )
        ]

    edge_by_id = {edge["edge_id"]: edge for edge in selector["state_edge_catalog"]}
    event_by_id = {event["event_id"]: event for event in selector["events"]}
    issues: set[str] = set()

    def case_records(event_id: str) -> list[dict[str, Any]]:
        event = event_by_id.get(event_id)
        if event is None:
            issues.add(f"{event_id}:MISSING_EVENT")
            return []
        records: list[dict[str, Any]] = []
        for transition_case in event["transition_cases"]:
            edges_by_domain = {
                domain_id: [
                    edge_by_id[edge_ref]
                    for edge_ref in transition_case["state_edge_refs"]
                    if edge_by_id[edge_ref]["state_domain"] == domain_id
                ]
                for domain_id in required_domains
            }
            if any(len(edges) != 1 for edges in edges_by_domain.values()):
                issues.add(
                    f"{event_id}."
                    f"{transition_case['semantic_case_id']}:"
                    "REQUIRES_ONE_EXPLICIT_OUTER_LOCAL_AND_OPERATION_EDGE"
                )
                continue
            records.append(
                {
                    "case": transition_case,
                    "event": event,
                    "kind_scope": (
                        _observer_grant_request_case_kind_scope(
                            event=event,
                            evidence_variant_id=transition_case["evidence_variant_id"],
                        )
                    ),
                    "local": edges_by_domain["LOCAL_GRANT_STATE"][0],
                    "operation": edges_by_domain[
                        "OBSERVER_GRANT_REQUEST_OPERATION_STATE"
                    ][0],
                    "outer": edges_by_domain["OUTER_LIFECYCLE"][0],
                    "resolution_cause": (
                        _observer_grant_request_case_resolution_cause(
                            event=event,
                            evidence_variant_id=transition_case["evidence_variant_id"],
                        )
                    ),
                    "variant_id": transition_case["evidence_variant_id"],
                }
            )
        return records

    def pair(record: dict[str, Any], axis: str) -> tuple[str, str]:
        edge = record[axis]
        return edge["from_state"], edge["to_state"]

    def exact_case_kind(record: dict[str, Any]) -> str | None:
        kind_scope = record["kind_scope"]
        if len(kind_scope) != 1:
            issues.add(
                f"{record['event']['event_id']}."
                f"{record['case']['semantic_case_id']}:"
                "CASE_MUST_DERIVE_EXACTLY_ONE_REQUEST_KIND"
            )
            return None
        return next(iter(kind_scope))

    allowed_outer_self_pairs = {
        (phase, phase) for phase in OBSERVER_GRANT_REQUEST_RESOLUTION_OUTER_PHASES
    }

    prepare_local_pair_by_kind = {
        "ATTACH": ("PENDING_FIRST_ATTACH", "PENDING_FIRST_ATTACH"),
        "REATTACH": ("TERMINAL", "TERMINAL"),
        "RENEW": ("LIVE", "LIVE"),
    }
    prepare_records = case_records(OBSERVER_GRANT_REQUEST_PREPARE_EVENT)
    covered_prepare_kinds: set[str] = set()
    for record in prepare_records:
        kind = exact_case_kind(record)
        if kind is None:
            continue
        covered_prepare_kinds.add(kind)
        if (
            pair(record, "outer") != ("OPEN_ADMISSION", "OPEN_ADMISSION")
            or pair(record, "local") != prepare_local_pair_by_kind[kind]
        ):
            issues.add(
                f"{OBSERVER_GRANT_REQUEST_PREPARE_EVENT}."
                f"{record['case']['semantic_case_id']}:"
                f"INVALID_{kind}_PREPARE_PRODUCT"
            )
    if covered_prepare_kinds != set(OBSERVER_GRANT_REQUEST_KINDS):
        issues.add(
            f"{OBSERVER_GRANT_REQUEST_PREPARE_EVENT}:"
            "KIND_COVERAGE_MUST_EQUAL_"
            f"{sorted(OBSERVER_GRANT_REQUEST_KINDS)!r}_"
            f"ACTUAL_{sorted(covered_prepare_kinds)!r}"
        )

    begin_contract_by_event = {
        "BEGIN_OBSERVER_GRANT_ATTACH_REQUEST": (
            "ATTACH",
            ("PENDING_FIRST_ATTACH", "PENDING_FIRST_ATTACH"),
        ),
        "BEGIN_OBSERVER_GRANT_REATTACH_REQUEST": (
            "REATTACH",
            ("TERMINAL", "TERMINAL"),
        ),
        "BEGIN_OBSERVER_GRANT_RENEWAL_REQUEST": (
            "RENEW",
            ("LIVE", "LIVE_RENEW_PENDING"),
        ),
    }
    for event_id, (
        expected_kind,
        expected_local_pair,
    ) in begin_contract_by_event.items():
        records = case_records(event_id)
        actual_product_pairs = {
            (
                pair(record, "outer"),
                pair(record, "local"),
                pair(record, "operation"),
            )
            for record in records
        }
        expected_product_pairs = {
            (
                ("OPEN_ADMISSION", "OPEN_ADMISSION"),
                expected_local_pair,
                ("INTENT_PREPARED", "PENDING_RESPONSE"),
            )
        }
        if actual_product_pairs != expected_product_pairs:
            issues.add(
                f"{event_id}:{expected_kind}_BEGIN_PRODUCT_MUST_EQUAL_"
                f"{sorted(expected_product_pairs)!r}_"
                f"ACTUAL_{sorted(actual_product_pairs)!r}"
            )

    ambiguity_allowed_local_pairs = {
        "ATTACH": {
            ("PENDING_FIRST_ATTACH", "PENDING_FIRST_ATTACH"),
            ("PENDING_FIRST_ATTACH", "TERMINAL"),
            ("TERMINAL", "TERMINAL"),
        },
        "REATTACH": {("TERMINAL", "TERMINAL")},
        "RENEW": {
            ("DETACH_PENDING", "DETACH_PENDING"),
            ("LIVE_RENEW_PENDING", "LIVE_RENEW_PENDING"),
            (
                "LIVE_RENEW_PENDING",
                "RENEW_PENDING_PREDECESSOR_CLOSED",
            ),
            (
                "RENEW_PENDING_PREDECESSOR_CLOSED",
                "RENEW_PENDING_PREDECESSOR_CLOSED",
            ),
            ("TERMINAL", "TERMINAL"),
        },
    }
    ambiguity_records = case_records(OBSERVER_GRANT_REQUEST_AMBIGUITY_EVENT)
    ambiguity_coverage: set[tuple[str, str]] = set()
    for record in ambiguity_records:
        kind = exact_case_kind(record)
        if kind is None:
            continue
        outer_pair = pair(record, "outer")
        local_pair = pair(record, "local")
        if outer_pair not in allowed_outer_self_pairs:
            issues.add(
                f"{OBSERVER_GRANT_REQUEST_AMBIGUITY_EVENT}."
                f"{record['case']['semantic_case_id']}:"
                "OUTER_PHASE_MUST_BE_PRESERVED_AND_DENY_ONLY"
            )
            continue
        ambiguity_coverage.add((kind, outer_pair[0]))
        if local_pair not in ambiguity_allowed_local_pairs[kind]:
            issues.add(
                f"{OBSERVER_GRANT_REQUEST_AMBIGUITY_EVENT}."
                f"{record['case']['semantic_case_id']}:"
                f"UNSAFE_{kind}_LOCAL_EDGE_{local_pair!r}"
            )
        if outer_pair[0] != "OPEN_ADMISSION" and local_pair[1] in {
            "LIVE",
            "LIVE_RENEW_PENDING",
            "PENDING_FIRST_ATTACH",
        }:
            issues.add(
                f"{OBSERVER_GRANT_REQUEST_AMBIGUITY_EVENT}."
                f"{record['case']['semantic_case_id']}:"
                "DENY_PHASE_MUST_NOT_PRESERVE_ADMISSION_AUTHORITY"
            )
    expected_resolution_coverage = {
        (kind, phase)
        for kind in OBSERVER_GRANT_REQUEST_KINDS
        for phase in OBSERVER_GRANT_REQUEST_RESOLUTION_OUTER_PHASES
    }
    if ambiguity_coverage != expected_resolution_coverage:
        issues.add(
            f"{OBSERVER_GRANT_REQUEST_AMBIGUITY_EVENT}:"
            "KIND_OUTER_PHASE_COVERAGE_MUST_EQUAL_"
            f"{sorted(expected_resolution_coverage)!r}_"
            f"ACTUAL_{sorted(ambiguity_coverage)!r}"
        )

    intent_resolution_records = case_records(
        OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT
    )
    unused_causes = {
        "SERVER_SLOT_CANCELED_UNUSED",
        "SERVER_SLOT_EXPIRED_UNUSED",
    }
    intent_resolution_coverage: set[tuple[str, str, str, tuple[str, str]]] = set()
    expected_intent_local_pairs: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for phase in OBSERVER_GRANT_REQUEST_RESOLUTION_OUTER_PHASES:
        is_open = phase == "OPEN_ADMISSION"
        expected_intent_local_pairs[("ATTACH", phase)] = {
            (
                "PENDING_FIRST_ATTACH",
                "PENDING_FIRST_ATTACH" if is_open else "TERMINAL",
            ),
            ("TERMINAL", "TERMINAL"),
        }
        expected_intent_local_pairs[("REATTACH", phase)] = {("TERMINAL", "TERMINAL")}
        expected_intent_local_pairs[("RENEW", phase)] = {
            ("LIVE", "LIVE" if is_open else "DETACH_PENDING"),
            ("DETACH_PENDING", "DETACH_PENDING"),
            ("TERMINAL", "TERMINAL"),
        }
    for record in intent_resolution_records:
        kind = exact_case_kind(record)
        if kind is None:
            continue
        cause = record["resolution_cause"]
        if cause not in unused_causes:
            issues.add(
                f"{OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT}."
                f"{record['case']['semantic_case_id']}:"
                f"FORBIDDEN_NON_UNUSED_CAUSE_{cause}"
            )
            continue
        outer_pair = pair(record, "outer")
        local_pair = pair(record, "local")
        if outer_pair not in allowed_outer_self_pairs:
            issues.add(
                f"{OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT}."
                f"{record['case']['semantic_case_id']}:"
                "OUTER_PHASE_MUST_BE_PRESERVED_AND_CLOSURE_ONLY"
            )
            continue
        outer_source = outer_pair[0]
        intent_resolution_coverage.add((kind, cause, outer_source, local_pair))
        if local_pair not in expected_intent_local_pairs[(kind, outer_source)]:
            issues.add(
                f"{OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT}."
                f"{record['case']['semantic_case_id']}:"
                f"INVALID_{kind}_{outer_source}_LOCAL_EDGE_{local_pair!r}"
            )
    expected_intent_resolution_coverage = {
        (kind, cause, phase, local_pair)
        for kind in OBSERVER_GRANT_REQUEST_KINDS
        for cause in unused_causes
        for phase in OBSERVER_GRANT_REQUEST_RESOLUTION_OUTER_PHASES
        for local_pair in expected_intent_local_pairs[(kind, phase)]
    }
    if intent_resolution_coverage != expected_intent_resolution_coverage:
        issues.add(
            f"{OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT}:"
            "KIND_CAUSE_OUTER_PHASE_COVERAGE_MUST_EQUAL_"
            f"{sorted(expected_intent_resolution_coverage)!r}_"
            f"ACTUAL_{sorted(intent_resolution_coverage)!r}"
        )

    observation_records = case_records(
        OBSERVER_GRANT_REQUEST_TERMINAL_OBSERVATION_EVENT
    )
    allowed_observation_local_pairs_by_kind = {
        "ATTACH": {
            ("PENDING_FIRST_ATTACH", "TERMINAL"),
            ("TERMINAL", "TERMINAL"),
        },
        "REATTACH": {("TERMINAL", "TERMINAL")},
        "RENEW": {
            ("DETACH_PENDING", "DETACH_PENDING"),
            (
                "LIVE_RENEW_PENDING",
                "RENEW_PENDING_PREDECESSOR_CLOSED",
            ),
            (
                "RENEW_PENDING_PREDECESSOR_CLOSED",
                "RENEW_PENDING_PREDECESSOR_CLOSED",
            ),
            ("TERMINAL", "TERMINAL"),
        },
    }
    required_observation_local_pairs_by_kind = {
        "ATTACH": {("PENDING_FIRST_ATTACH", "TERMINAL")},
        "REATTACH": {("TERMINAL", "TERMINAL")},
        "RENEW": {
            (
                "LIVE_RENEW_PENDING",
                "RENEW_PENDING_PREDECESSOR_CLOSED",
            ),
            (
                "RENEW_PENDING_PREDECESSOR_CLOSED",
                "RENEW_PENDING_PREDECESSOR_CLOSED",
            ),
        },
    }
    actual_observation_local_pairs_by_kind = {
        kind: set() for kind in OBSERVER_GRANT_REQUEST_KINDS
    }
    observation_coverage: set[tuple[str, str, str]] = set()
    for record in observation_records:
        kind = exact_case_kind(record)
        if kind is None:
            continue
        local_pair = pair(record, "local")
        actual_observation_local_pairs_by_kind[kind].add(local_pair)
        if local_pair not in allowed_observation_local_pairs_by_kind[kind]:
            issues.add(
                f"{OBSERVER_GRANT_REQUEST_TERMINAL_OBSERVATION_EVENT}."
                f"{record['case']['semantic_case_id']}:"
                f"UNSAFE_{kind}_LOCAL_EDGE_{local_pair!r}"
            )
        if pair(record, "outer") not in allowed_outer_self_pairs:
            issues.add(
                f"{OBSERVER_GRANT_REQUEST_TERMINAL_OBSERVATION_EVENT}."
                f"{record['case']['semantic_case_id']}:"
                "OUTER_PHASE_MUST_BE_PRESERVED_AND_CLOSURE_ONLY"
            )
            continue
        observation_coverage.add(
            (
                kind,
                record["operation"]["from_state"],
                record["outer"]["from_state"],
            )
        )
    for kind in sorted(OBSERVER_GRANT_REQUEST_KINDS):
        missing_local_pairs = (
            required_observation_local_pairs_by_kind[kind]
            - actual_observation_local_pairs_by_kind[kind]
        )
        if missing_local_pairs:
            issues.add(
                f"{OBSERVER_GRANT_REQUEST_TERMINAL_OBSERVATION_EVENT}."
                f"{kind}:MISSING_LOCAL_EDGES_"
                f"{sorted(missing_local_pairs)!r}"
            )
    expected_observation_coverage = {
        (kind, operation_source, phase)
        for kind in OBSERVER_GRANT_REQUEST_KINDS
        for operation_source in (
            "AMBIGUOUS_SERVER_ACCEPTANCE",
            "PENDING_RESPONSE",
            "TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE",
        )
        for phase in OBSERVER_GRANT_REQUEST_RESOLUTION_OUTER_PHASES
    }
    if observation_coverage != expected_observation_coverage:
        issues.add(
            f"{OBSERVER_GRANT_REQUEST_TERMINAL_OBSERVATION_EVENT}:"
            "KIND_OPERATION_OUTER_PHASE_COVERAGE_MUST_EQUAL_"
            f"{sorted(expected_observation_coverage)!r}_"
            f"ACTUAL_{sorted(observation_coverage)!r}"
        )

    expected_install_local_pairs = {
        "INSTALL_OBSERVER_GRANT_FROM_ACCEPTED_RESPONSE": {
            ("PENDING_FIRST_ATTACH", "LIVE")
        },
        "INSTALL_OBSERVER_GRANT_REATTACHMENT_FROM_ACCEPTED_RESPONSE": {
            ("TERMINAL", "LIVE")
        },
        "INSTALL_OBSERVER_GRANT_RENEWAL_FROM_ACCEPTED_RESPONSE": {
            ("LIVE_RENEW_PENDING", "LIVE"),
            ("RENEW_PENDING_PREDECESSOR_CLOSED", "LIVE"),
        },
    }
    for event_id, expected_local_pairs in expected_install_local_pairs.items():
        records = case_records(event_id)
        actual_local_pairs = {pair(record, "local") for record in records}
        if actual_local_pairs != expected_local_pairs:
            issues.add(
                f"{event_id}:LOCAL_EDGE_SET_MUST_EQUAL_"
                f"{sorted(expected_local_pairs)!r}_"
                f"ACTUAL_{sorted(actual_local_pairs)!r}"
            )
        actual_outer_pairs = {pair(record, "outer") for record in records}
        if actual_outer_pairs != {("OPEN_ADMISSION", "OPEN_ADMISSION")}:
            issues.add(
                f"{event_id}:INSTALL_OUTER_EDGE_MUST_EQUAL_"
                "OPEN_ADMISSION_SELF_ONLY_"
                f"ACTUAL_{sorted(actual_outer_pairs)!r}"
            )

    resolver_kind_by_event = {
        "RESOLVE_OBSERVER_GRANT_ATTACH_REQUEST_WITHOUT_INSTALLATION": ("ATTACH"),
        "RESOLVE_OBSERVER_GRANT_REATTACH_REQUEST_WITHOUT_INSTALLATION": ("REATTACH"),
        "RESOLVE_OBSERVER_GRANT_RENEWAL_WITHOUT_INSTALLATION": "RENEW",
    }
    unused_causes = {
        "SERVER_SLOT_CANCELED_UNUSED",
        "SERVER_SLOT_EXPIRED_UNUSED",
    }
    accepted_cause = "ACCEPTED_GRANT_FULLY_CLOSED_WITHOUT_LOCAL_INSTALLATION"
    expected_operation_sources = {
        accepted_cause: {"TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE"},
        **{
            cause: {
                "AMBIGUOUS_SERVER_ACCEPTANCE",
                "PENDING_RESPONSE",
            }
            for cause in unused_causes
        },
    }

    def expected_resolver_local_pairs(
        *,
        kind: str,
        cause: str,
        phase: str,
    ) -> set[tuple[str, str]]:
        if kind in {"ATTACH", "REATTACH"} and cause == accepted_cause:
            return {("TERMINAL", "TERMINAL")}
        if kind == "ATTACH":
            return {
                (
                    "PENDING_FIRST_ATTACH",
                    "PENDING_FIRST_ATTACH" if phase == "OPEN_ADMISSION" else "TERMINAL",
                ),
                ("TERMINAL", "TERMINAL"),
            }
        if kind == "REATTACH":
            return {("TERMINAL", "TERMINAL")}
        if cause == accepted_cause:
            return {
                ("RENEW_PENDING_PREDECESSOR_CLOSED", "TERMINAL"),
                ("TERMINAL", "TERMINAL"),
            }
        if phase == "OPEN_ADMISSION":
            return {
                ("DETACH_PENDING", "DETACH_PENDING"),
                ("LIVE_RENEW_PENDING", "LIVE"),
                ("LIVE_RENEW_PENDING", "TERMINAL"),
                ("RENEW_PENDING_PREDECESSOR_CLOSED", "TERMINAL"),
                ("TERMINAL", "TERMINAL"),
            }
        return {
            ("DETACH_PENDING", "DETACH_PENDING"),
            ("LIVE_RENEW_PENDING", "DETACH_PENDING"),
            ("RENEW_PENDING_PREDECESSOR_CLOSED", "TERMINAL"),
            ("TERMINAL", "TERMINAL"),
        }

    for event_id, kind in resolver_kind_by_event.items():
        records = case_records(event_id)
        deadline_by_id = {
            condition["condition_id"]: condition
            for condition in event_by_id.get(
                event_id,
                {"deadline_conditions": {"conditions": []}},
            )["deadline_conditions"]["conditions"]
        }
        for record in records:
            cause = record["resolution_cause"]
            if cause not in OBSERVER_GRANT_REQUEST_TERMINAL_RESOLUTION_CAUSES:
                continue
            outer_pair = pair(record, "outer")
            local_pair = pair(record, "local")
            if outer_pair not in allowed_outer_self_pairs:
                issues.add(
                    f"{event_id}."
                    f"{record['case']['semantic_case_id']}:"
                    "OUTER_PHASE_MUST_BE_PRESERVED_AND_CLOSURE_ONLY"
                )
            outer_source = record["outer"]["from_state"]
            local_source, local_target = local_pair
            if kind == "REATTACH" and local_pair != (
                "TERMINAL",
                "TERMINAL",
            ):
                issues.add(
                    f"{event_id}.{cause}:REATTACH_MUST_PRESERVE_"
                    f"TERMINAL_NOT_{local_pair!r}"
                )
            if cause == accepted_cause and local_target == "LIVE":
                issues.add(
                    f"{event_id}.{cause}:ACCEPTED_CLOSED_CAUSE_"
                    "MUST_NEVER_INSTALL_OR_RESTORE_LIVE"
                )
            if kind == "ATTACH":
                allowed_targets = (
                    {"PENDING_FIRST_ATTACH", "TERMINAL"}
                    if cause in unused_causes
                    else {"TERMINAL"}
                )
                if local_target not in allowed_targets or (
                    outer_source != "OPEN_ADMISSION" and local_target != "TERMINAL"
                ):
                    issues.add(
                        f"{event_id}.{cause}:ATTACH_LOCAL_SUCCESSOR_"
                        f"POLARITY_INVALID_{local_pair!r}_AT_"
                        f"{outer_source}"
                    )
            if kind == "RENEW":
                if local_target == "LIVE":
                    if (
                        cause not in unused_causes
                        or local_source != "LIVE_RENEW_PENDING"
                        or outer_source != "OPEN_ADMISSION"
                    ):
                        issues.add(
                            f"{event_id}.{cause}:LIVE_RESTORATION_"
                            f"POLARITY_INVALID_{local_pair!r}_AT_"
                            f"{outer_source}"
                        )
                    conditions = [
                        deadline_by_id[condition_id]
                        for condition_id in record["case"]["case_contract"][
                            "deadline_condition_ids"
                        ]
                        if condition_id in deadline_by_id
                    ]
                    if not any(
                        condition["comparison"] == "STRICTLY_BEFORE"
                        and condition["deadline_kind"]
                        == ("OBSERVER_RENEWAL_PREDECESSOR_ADMISSION_NOT_AFTER")
                        for condition in conditions
                    ):
                        issues.add(
                            f"{event_id}.{cause}:LIVE_RESTORATION_"
                            "REQUIRES_STRICT_BEFORE_ORIGINAL_"
                            "PREDECESSOR_DEADLINE"
                        )
                elif outer_source != "OPEN_ADMISSION" and local_target not in {
                    "DETACH_PENDING",
                    "TERMINAL",
                }:
                    issues.add(
                        f"{event_id}.{cause}:DENY_PHASE_RENEWAL_"
                        f"SUCCESSOR_IS_NOT_RESTRICTIVE_{local_pair!r}"
                    )

        actual_resolver_rows = {
            (
                record["resolution_cause"],
                record["operation"]["from_state"],
                record["outer"]["from_state"],
                pair(record, "local"),
            )
            for record in records
            if record["resolution_cause"]
            in OBSERVER_GRANT_REQUEST_TERMINAL_RESOLUTION_CAUSES
        }
        expected_resolver_rows = {
            (cause, operation_source, phase, local_pair)
            for cause, operation_sources in expected_operation_sources.items()
            for operation_source in operation_sources
            for phase in OBSERVER_GRANT_REQUEST_RESOLUTION_OUTER_PHASES
            for local_pair in expected_resolver_local_pairs(
                kind=kind,
                cause=cause,
                phase=phase,
            )
        }
        if actual_resolver_rows != expected_resolver_rows:
            issues.add(
                f"{event_id}:CAUSE_OPERATION_OUTER_LOCAL_ROW_SET_MUST_EQUAL_"
                f"{sorted(expected_resolver_rows)!r}_"
                f"ACTUAL_{sorted(actual_resolver_rows)!r}"
            )
    return sorted(issues)


def _observer_grant_request_evidence_contract_issues(
    selector: dict[str, Any],
) -> list[str]:
    """Require explicit, disjoint evidence for each causal request outcome."""

    event_by_id = {event["event_id"]: event for event in selector["events"]}
    issues: set[str] = set()

    def variants(
        event_id: str,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        event = event_by_id.get(event_id)
        if event is None:
            issues.add(f"{event_id}:MISSING_EVENT")
            return None, []
        return (
            event,
            event["decision_model"]["evidence_variant_definitions"],
        )

    def require_variant_evidence(
        *,
        event: dict[str, Any],
        variant: dict[str, Any],
        required_fields: set[str],
        forbidden_fields: set[str] = frozenset(),
    ) -> None:
        event_id = event["event_id"]
        variant_id = variant["evidence_variant_id"]
        declared_required = set(
            event["decision_model"]["common_required_fields"]
        ) | set(variant["required_fields"])
        declared_forbidden = set(variant["forbidden_fields"])
        missing_required = required_fields - declared_required
        missing_forbidden = forbidden_fields - declared_forbidden
        truth_fields = {condition["field"] for condition in variant["truth_conditions"]}
        missing_truth_conditions = required_fields - truth_fields
        if missing_required:
            issues.add(
                f"{event_id}.{variant_id}:MISSING_REQUIRED_FIELDS_"
                f"{sorted(missing_required)!r}"
            )
        if missing_forbidden:
            issues.add(
                f"{event_id}.{variant_id}:MISSING_FORBIDDEN_FIELDS_"
                f"{sorted(missing_forbidden)!r}"
            )
        if missing_truth_conditions:
            issues.add(
                f"{event_id}.{variant_id}:MISSING_TRUTH_CONDITIONS_"
                f"{sorted(missing_truth_conditions)!r}"
            )
        exact_operator_by_field = {
            OBSERVER_GRANT_ACTIVATION_PUBLICATION_MANIFEST_FIELD: (
                OBSERVER_GRANT_ACTIVATION_PUBLICATION_MANIFEST_OPERATOR
            )
        }
        for field, operator in exact_operator_by_field.items():
            if field not in required_fields:
                continue
            if not any(
                condition["field"] == field
                and condition["operator"] == operator
                and condition["value"] is True
                for condition in variant["truth_conditions"]
            ):
                issues.add(f"{event_id}.{variant_id}:{field}_MUST_USE_{operator}")
        overlap = declared_required & declared_forbidden
        if overlap:
            issues.add(
                f"{event_id}.{variant_id}:REQUIRED_FORBIDDEN_OVERLAP_"
                f"{sorted(overlap)!r}"
            )

    def exact_variant_value(
        *,
        event: dict[str, Any],
        variant: dict[str, Any],
        field: str,
        allowed_values: frozenset[str],
    ) -> str | None:
        variant_id = variant["evidence_variant_id"]
        declared_required = set(
            event["decision_model"]["common_required_fields"]
        ) | set(variant["required_fields"])
        if field not in declared_required:
            issues.add(
                f"{event['event_id']}.{variant_id}:MISSING_REQUIRED_FIELDS_{[field]!r}"
            )
        derived_values = {
            condition["value"]
            for condition in variant["truth_conditions"]
            if condition["field"] == field
            and condition["operator"] == "EQUALS"
            and condition["value"] in allowed_values
        }
        if len(derived_values) != 1:
            issues.add(
                f"{event['event_id']}.{variant_id}:"
                f"{field}_MUST_DERIVE_EXACTLY_ONE_CLOSED_VALUE"
            )
            return None
        return next(iter(derived_values))

    for event_id in sorted(
        OBSERVER_GRANT_REQUEST_SHARED_KIND_EVENTS
        - {OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT}
    ):
        event, event_variants = variants(event_id)
        if event is None:
            continue
        derived_kinds = {
            kind
            for variant in event_variants
            if (
                kind := exact_variant_value(
                    event=event,
                    variant=variant,
                    field=OBSERVER_GRANT_REQUEST_KIND_FIELD,
                    allowed_values=OBSERVER_GRANT_REQUEST_KINDS,
                )
            )
            is not None
        }
        if derived_kinds != set(OBSERVER_GRANT_REQUEST_KINDS):
            issues.add(
                f"{event_id}:KIND_VARIANT_COVERAGE_MUST_EQUAL_"
                f"{sorted(OBSERVER_GRANT_REQUEST_KINDS)!r}_"
                f"ACTUAL_{sorted(derived_kinds)!r}"
            )

    intent_event, intent_variants = variants(
        OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT
    )
    if intent_event is not None:
        unused_causes = frozenset(
            {
                "SERVER_SLOT_CANCELED_UNUSED",
                "SERVER_SLOT_EXPIRED_UNUSED",
            }
        )
        covered_kind_causes: set[tuple[str, str]] = set()
        for variant in intent_variants:
            kind = exact_variant_value(
                event=intent_event,
                variant=variant,
                field=OBSERVER_GRANT_REQUEST_KIND_FIELD,
                allowed_values=OBSERVER_GRANT_REQUEST_KINDS,
            )
            cause = exact_variant_value(
                event=intent_event,
                variant=variant,
                field=OBSERVER_GRANT_REQUEST_INTENT_CAUSE_FIELD,
                allowed_values=unused_causes,
            )
            require_variant_evidence(
                event=intent_event,
                variant=variant,
                required_fields={
                    OBSERVER_GRANT_REQUEST_EXACT_INTENT_FIELD,
                    OBSERVER_GRANT_REQUEST_INTENT_CAUSE_FIELD,
                    OBSERVER_GRANT_REQUEST_KIND_FIELD,
                    OBSERVER_GRANT_REQUEST_VERIFICATION_FIELD,
                    *OBSERVER_GRANT_REQUEST_UNUSED_EVIDENCE_FIELDS,
                },
                forbidden_fields={
                    *OBSERVER_GRANT_REQUEST_ACCEPTED_CLOSURE_EVIDENCE_FIELDS,
                    *(
                        OBSERVER_GRANT_REQUEST_INSTALL_EVIDENCE_FIELDS
                        - {OBSERVER_GRANT_REQUEST_VERIFICATION_FIELD}
                    ),
                },
            )
            if kind is not None and cause is not None:
                covered_kind_causes.add((kind, cause))
        expected_kind_causes = {
            (kind, cause)
            for kind in OBSERVER_GRANT_REQUEST_KINDS
            for cause in unused_causes
        }
        if covered_kind_causes != expected_kind_causes:
            issues.add(
                f"{OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT}:"
                "KIND_CAUSE_VARIANT_COVERAGE_MUST_EQUAL_"
                f"{sorted(expected_kind_causes)!r}_"
                f"ACTUAL_{sorted(covered_kind_causes)!r}"
            )

    observation_event, observation_variants = variants(
        OBSERVER_GRANT_REQUEST_TERMINAL_OBSERVATION_EVENT
    )
    if observation_event is not None:
        for variant in observation_variants:
            require_variant_evidence(
                event=observation_event,
                variant=variant,
                required_fields=set(OBSERVER_GRANT_REQUEST_OBSERVATION_EVIDENCE_FIELDS)
                | {OBSERVER_GRANT_REQUEST_KIND_FIELD},
                forbidden_fields=set(
                    OBSERVER_GRANT_REQUEST_ACCEPTED_CLOSURE_EVIDENCE_FIELDS
                ),
            )

    for event_id in sorted(OBSERVER_GRANT_REQUEST_INSTALL_EVENTS):
        event, event_variants = variants(event_id)
        if event is None:
            continue
        for variant in event_variants:
            require_variant_evidence(
                event=event,
                variant=variant,
                required_fields=(
                    set(OBSERVER_GRANT_REQUEST_INSTALL_EVIDENCE_FIELDS)
                    | set(
                        OBSERVER_GRANT_REQUEST_INSTALL_ADDITIONAL_EVIDENCE_FIELDS[
                            event_id
                        ]
                    )
                ),
                forbidden_fields=(
                    set(OBSERVER_GRANT_REQUEST_UNUSED_EVIDENCE_FIELDS)
                    | set(OBSERVER_GRANT_REQUEST_ACCEPTED_CLOSURE_EVIDENCE_FIELDS)
                ),
            )

    for event_id in sorted(OBSERVER_GRANT_REQUEST_RESOLVER_EVENTS):
        event, event_variants = variants(event_id)
        if event is None:
            continue
        for variant in event_variants:
            cause = exact_variant_value(
                event=event,
                variant=variant,
                field=OBSERVER_GRANT_REQUEST_CAUSE_FIELD,
                allowed_values=(OBSERVER_GRANT_REQUEST_TERMINAL_RESOLUTION_CAUSES),
            )
            if cause is None:
                continue
            if cause == ("ACCEPTED_GRANT_FULLY_CLOSED_WITHOUT_LOCAL_INSTALLATION"):
                cause_evidence_fields = (
                    OBSERVER_GRANT_REQUEST_ACCEPTED_CLOSURE_EVIDENCE_FIELDS
                )
                opposite_evidence_fields = OBSERVER_GRANT_REQUEST_UNUSED_EVIDENCE_FIELDS
            else:
                cause_evidence_fields = OBSERVER_GRANT_REQUEST_UNUSED_EVIDENCE_FIELDS
                opposite_evidence_fields = (
                    OBSERVER_GRANT_REQUEST_ACCEPTED_CLOSURE_EVIDENCE_FIELDS
                )
            required_fields = {
                OBSERVER_GRANT_REQUEST_CAUSE_FIELD,
                OBSERVER_GRANT_REQUEST_EXACT_ATTEMPT_FIELD,
                OBSERVER_GRANT_REQUEST_VERIFICATION_FIELD,
                *cause_evidence_fields,
            }
            require_variant_evidence(
                event=event,
                variant=variant,
                required_fields=required_fields,
                forbidden_fields=opposite_evidence_fields,
            )
            cause_conditions = [
                condition
                for condition in variant["truth_conditions"]
                if condition["field"] == OBSERVER_GRANT_REQUEST_CAUSE_FIELD
            ]
            if not any(
                condition["operator"] == "EQUALS" and condition["value"] == cause
                for condition in cause_conditions
            ):
                issues.add(
                    f"{event_id}.{cause}:CAUSE_MUST_BE_VERIFIER_"
                    "DERIVED_BY_EXACT_EQUALITY"
                )
    return sorted(issues)


def _cross_store_publication_manifest_contract_issues(
    data: dict[str, Any],
) -> list[str]:
    """Reject protected envelopes outside an exact complete publication.

    Activation consumes one protected envelope, so its decision variant binds
    one top-level publication bundle. Closure aggregation consumes a bounded
    per-member evidence bijection. Its boundary-return arms bind publication
    bundles inside the corresponding member records; source-local, elapsed, or
    qualified-isolation arms must forbid those fields. A singular top-level
    closure bundle would be ambiguous for a mixed or multi-member batch and is
    therefore forbidden for every aggregation variant.
    """

    selector_by_id = {
        selector["selector_id"]: selector for selector in data["selectors"]
    }
    issues: set[str] = set()

    selector_id = "TRUSTED_DELIVERY_RELEASE"
    event_id = TRUSTED_DELIVERY_BOUNDARY_ACTIVATION_EVENT
    selector = selector_by_id.get(selector_id)
    if selector is None:
        issues.add(f"{selector_id}:MISSING_SELECTOR")
    else:
        event = next(
            (item for item in selector["events"] if item["event_id"] == event_id),
            None,
        )
        if event is None:
            issues.add(f"{selector_id}.{event_id}:MISSING_EVENT")
        else:
            required_fields = {
                CROSS_STORE_PRODUCER_COMPLETION_MANIFEST_FIELD,
                CROSS_STORE_PROTECTED_OUTPUT_DELIVERY_CAPSULE_FIELD,
                OBSERVER_GRANT_REQUEST_VERIFICATION_FIELD,
                TRUSTED_DELIVERY_BOUNDARY_ACTIVATION_ENVELOPE_FIELD,
                TRUSTED_DELIVERY_BOUNDARY_ACTIVATION_MANIFEST_FIELD,
            }
            exact_operators = {
                CROSS_STORE_PRODUCER_COMPLETION_MANIFEST_FIELD: (
                    CROSS_STORE_EXACT_OPERATION_VERIFICATION_OPERATOR
                ),
                CROSS_STORE_PROTECTED_OUTPUT_DELIVERY_CAPSULE_FIELD: (
                    CROSS_STORE_EXACT_OPERATION_VERIFICATION_OPERATOR
                ),
                OBSERVER_GRANT_REQUEST_VERIFICATION_FIELD: (
                    CROSS_STORE_EXACT_OPERATION_VERIFICATION_OPERATOR
                ),
                TRUSTED_DELIVERY_BOUNDARY_ACTIVATION_ENVELOPE_FIELD: (
                    CROSS_STORE_EXACT_OPERATION_VERIFICATION_OPERATOR
                ),
                TRUSTED_DELIVERY_BOUNDARY_ACTIVATION_MANIFEST_FIELD: (
                    TRUSTED_DELIVERY_BOUNDARY_ACTIVATION_MANIFEST_OPERATOR
                ),
            }
            variants = event["decision_model"]["evidence_variant_definitions"]
            if not variants:
                issues.add(f"{selector_id}.{event_id}:MISSING_EVIDENCE_VARIANTS")
            for variant in variants:
                variant_id = variant["evidence_variant_id"]
                declared_required = set(
                    event["decision_model"]["common_required_fields"]
                ) | set(variant["required_fields"])
                missing_required = required_fields - declared_required
                if missing_required:
                    issues.add(
                        f"{selector_id}.{event_id}.{variant_id}:"
                        f"MISSING_REQUIRED_FIELDS_{sorted(missing_required)!r}"
                    )
                truth_conditions = variant["truth_conditions"]
                for field in sorted(required_fields):
                    if not any(
                        condition["field"] == field for condition in truth_conditions
                    ):
                        issues.add(
                            f"{selector_id}.{event_id}.{variant_id}:"
                            f"MISSING_TRUTH_CONDITION_{field}"
                        )
                for field, operator in exact_operators.items():
                    if not any(
                        condition["field"] == field
                        and condition["operator"] == operator
                        and condition["value"] is True
                        for condition in truth_conditions
                    ):
                        issues.add(
                            f"{selector_id}.{event_id}.{variant_id}:"
                            f"{field}_MUST_USE_{operator}"
                        )

    selector_id = "OBSERVER_ATTACHMENT_TARGET_HISTORY"
    event_id = OBSERVER_GRANT_CLOSURE_AGGREGATION_EVENT
    selector = selector_by_id.get(selector_id)
    if selector is None:
        issues.add(f"{selector_id}:MISSING_SELECTOR")
        return sorted(issues)
    event = next(
        (item for item in selector["events"] if item["event_id"] == event_id),
        None,
    )
    if event is None:
        issues.add(f"{selector_id}.{event_id}:MISSING_EVENT")
        return sorted(issues)

    publication_fields = {
        CROSS_STORE_PRODUCER_COMPLETION_MANIFEST_FIELD,
        CROSS_STORE_PROTECTED_OUTPUT_DELIVERY_CAPSULE_FIELD,
        OBSERVER_GRANT_REQUEST_VERIFICATION_FIELD,
        TRUSTED_DELIVERY_BOUNDARY_CLOSURE_ENVELOPE_FIELD,
        TRUSTED_DELIVERY_BOUNDARY_CLOSURE_MANIFEST_FIELD,
    }
    profile = data.get("observer_grant_request_target_profile", {}).get(
        "closure_aggregation_contract"
    )
    try:
        member_batch = profile["evidence_input"]["member_advance_batch"]
        authorization_arms = member_batch["per_member_authorization_origin"][
            "native_union_arms"
        ]
        transport_arms = member_batch["per_member_transport_origin"][
            "native_union_arms"
        ]
    except (KeyError, TypeError):
        issues.add(f"{selector_id}.{event_id}:INVALID_MEMBER_EVIDENCE_PROFILE")
        return sorted(issues)

    boundary_arm_paths = {
        ("AUTHORIZATION", "NO_INSTALL_ZERO_WORK_PROVED"),
        ("AUTHORIZATION", "TERMINAL_ACKED"),
        ("TRANSPORT", "EMERGENCY_COMPLETE_CLOSURE_TRANSPORT_QUIESCENT"),
        ("TRANSPORT", "TERMINAL_ENTRY_TRANSPORT_QUIESCENT"),
    }
    for family, arms in (
        ("AUTHORIZATION", authorization_arms),
        ("TRANSPORT", transport_arms),
    ):
        for arm_id, arm in arms.items():
            label = f"{selector_id}.{event_id}.{family}.{arm_id}"
            try:
                required = set(arm["required_fields"])
                forbidden = set(arm["forbidden_fields"])
            except (KeyError, TypeError):
                issues.add(f"{label}:INVALID_REQUIRED_FORBIDDEN_FIELDS")
                continue
            if (family, arm_id) in boundary_arm_paths:
                missing = (
                    OBSERVER_GRANT_CLOSURE_AGGREGATION_BOUNDARY_PUBLICATION_ARTIFACTS
                    - required
                )
                prohibited = (
                    OBSERVER_GRANT_CLOSURE_AGGREGATION_BOUNDARY_PUBLICATION_ARTIFACTS
                    & forbidden
                )
                if missing:
                    issues.add(
                        f"{label}:MISSING_BOUNDARY_PUBLICATION_ARTIFACTS_"
                        f"{sorted(missing)!r}"
                    )
                if prohibited:
                    issues.add(
                        f"{label}:REQUIRED_BOUNDARY_PUBLICATION_ARTIFACTS_FORBIDDEN_"
                        f"{sorted(prohibited)!r}"
                    )
            else:
                missing_forbidden = (
                    OBSERVER_GRANT_CLOSURE_AGGREGATION_BOUNDARY_PUBLICATION_ARTIFACTS
                    - forbidden
                )
                admitted = (
                    OBSERVER_GRANT_CLOSURE_AGGREGATION_BOUNDARY_PUBLICATION_ARTIFACTS
                    & required
                )
                if missing_forbidden:
                    issues.add(
                        f"{label}:LOCAL_ARM_ADMITS_BOUNDARY_PUBLICATION_ARTIFACTS_"
                        f"{sorted(missing_forbidden)!r}"
                    )
                if admitted:
                    issues.add(
                        f"{label}:LOCAL_ARM_REQUIRES_BOUNDARY_PUBLICATION_ARTIFACTS_"
                        f"{sorted(admitted)!r}"
                    )

    variants = event["decision_model"]["evidence_variant_definitions"]
    if not variants:
        issues.add(f"{selector_id}.{event_id}:MISSING_EVIDENCE_VARIANTS")
    for variant in variants:
        variant_id = variant["evidence_variant_id"]
        label = f"{selector_id}.{event_id}.{variant_id}"
        declared_required = set(
            event["decision_model"]["common_required_fields"]
        ) | set(variant["required_fields"])
        declared_forbidden = set(variant["forbidden_fields"])
        truth_conditions = variant["truth_conditions"]
        missing_forbidden = publication_fields - declared_forbidden
        if missing_forbidden:
            issues.add(
                f"{label}:AMBIGUOUS_TOP_LEVEL_BOUNDARY_PUBLICATION_FIELDS_"
                f"{sorted(missing_forbidden)!r}"
            )
        leaked_required = publication_fields & declared_required
        leaked_truth = {
            condition["field"]
            for condition in truth_conditions
            if condition["field"] in publication_fields
        }
        if leaked_required or leaked_truth:
            issues.add(
                f"{label}:SINGULAR_BOUNDARY_PUBLICATION_BUNDLE_"
                f"{sorted(leaked_required | leaked_truth)!r}"
            )
        input_kinds = {
            condition["value"]
            for condition in truth_conditions
            if condition["field"]
            == OBSERVER_GRANT_CLOSURE_AGGREGATION_EVIDENCE_INPUT_FIELD
            and condition["operator"] == "CLOSED_UNION_VARIANT_EQUALS"
        }
        if input_kinds == {"MEMBER_ADVANCE_BATCH"}:
            if (
                OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_EVIDENCE_BIJECTION_FIELD
                not in declared_required
            ):
                issues.add(f"{label}:MISSING_MEMBER_EVIDENCE_BIJECTION")
            if not any(
                condition["field"]
                == OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_EVIDENCE_BIJECTION_FIELD
                and condition["operator"]
                == OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_BIJECTION_OPERATOR
                and condition["value"] is True
                for condition in truth_conditions
            ):
                issues.add(f"{label}:MEMBER_EVIDENCE_BIJECTION_IS_NOT_EXACT")
        elif input_kinds == {"EXACT_EMPTY_ACCEPTED_PLAN"}:
            if (
                OBSERVER_GRANT_CLOSURE_AGGREGATION_EMPTY_UNIVERSE_PROOF_FIELD
                not in declared_required
            ):
                issues.add(f"{label}:MISSING_EMPTY_UNIVERSE_PROOF")
            if (
                OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_EVIDENCE_BIJECTION_FIELD
                not in declared_forbidden
            ):
                issues.add(f"{label}:EMPTY_UNIVERSE_ADMITS_MEMBER_EVIDENCE")
        else:
            issues.add(f"{label}:INVALID_EVIDENCE_INPUT_DISCRIMINANT")
    return sorted(issues)


def _observer_grant_closure_aggregation_profile_contract() -> dict[str, Any]:
    """Return the closed typed aggregate, head, and replay contract."""

    boundary_publication_artifacts = sorted(
        OBSERVER_GRANT_CLOSURE_AGGREGATION_BOUNDARY_PUBLICATION_ARTIFACTS
    )
    authorization_native_union_arms = {
        "BOUNDARY_PERMANENTLY_ISOLATED_WITH_COMPLETE_EXACT_WORK_PARTITION": {
            "forbidden_fields": [
                "BOUNDARY_TERMINAL_INSTALLATION_HIERARCHY",
                "DEADLINE_ELAPSED_PROOF",
                "NO_INSTALL_EVIDENCE",
                "PENDING_NEVER_LIVE_PROOF",
                "TRANSPORT_QUIESCENCE_EVIDENCE",
                "UNKNOWN_RETAINED_WORK_BOUND",
                *boundary_publication_artifacts,
            ],
            "required_fields": [
                "COMPLETE_EXACT_WORK_PARTITION",
                "QUALIFIED_ROLE_SPECIFIC_PERMANENT_ISOLATION_EVIDENCE",
            ],
            "to_state": "AUTH_CLOSED_EXACT",
        },
        "BOUNDARY_PERMANENTLY_ISOLATED_WITH_UNKNOWN_RETAINED_WORK": {
            "forbidden_fields": [
                "BOUNDARY_TERMINAL_INSTALLATION_HIERARCHY",
                "COMPLETE_EXACT_WORK_PARTITION",
                "DEADLINE_ELAPSED_PROOF",
                "NO_INSTALL_EVIDENCE",
                "PENDING_NEVER_LIVE_PROOF",
                "TRANSPORT_QUIESCENCE_EVIDENCE",
                *boundary_publication_artifacts,
            ],
            "required_fields": [
                "EXPLICIT_UNKNOWN_RETAINED_WORK",
                "QUALIFIED_ROLE_SPECIFIC_PERMANENT_ISOLATION_EVIDENCE",
                "UNKNOWN_RETAINED_WORK_BOUND",
            ],
            "to_state": "AUTH_CLOSED_UNKNOWN",
        },
        "DEADLINE_ELAPSED_UNACKNOWLEDGED_WITH_UNKNOWN_RETAINED_WORK": {
            "forbidden_fields": [
                "BOUNDARY_TERMINAL_INSTALLATION_HIERARCHY",
                "COMPLETE_EXACT_WORK_PARTITION",
                "NO_INSTALL_EVIDENCE",
                "PENDING_NEVER_LIVE_PROOF",
                "PERMANENT_ISOLATION_EVIDENCE",
                "TRANSPORT_QUIESCENCE_EVIDENCE",
                *boundary_publication_artifacts,
            ],
            "required_fields": [
                "CLOCK_RESTART_ANCESTRY_IF_APPLICABLE",
                "EXPLICIT_UNKNOWN_RETAINED_WORK",
                "ORIGINAL_BOUNDARY_RELEASE_NOT_AFTER",
                "QUALIFIED_NO_EXTENSION_MAPPING_AND_ELAPSED_PROOF",
                "UNKNOWN_RETAINED_WORK_BOUND",
            ],
            "to_state": "AUTH_CLOSED_UNKNOWN",
        },
        "NO_INSTALL_ZERO_WORK_PROVED": {
            "forbidden_fields": [
                "BOUNDARY_TERMINAL_INSTALLATION_HIERARCHY",
                "DEADLINE_ELAPSED_PROOF",
                "PERMANENT_ISOLATION_EVIDENCE",
                "PENDING_NEVER_LIVE_PROOF",
                "TRANSPORT_QUIESCENCE_EVIDENCE",
                "UNKNOWN_RETAINED_WORK_BOUND",
            ],
            "required_fields": [
                (
                    "trusted-delivery-boundary-grant-no-install-evidence-type::"
                    "TrustedDeliveryBoundaryGrantNoInstallEvidence"
                ),
                "EXACT_ZERO_WORK_ROOTS",
                *boundary_publication_artifacts,
            ],
            "to_state": "AUTH_CLOSED_EXACT",
        },
        "SERVER_TERMINAL_FROM_PENDING_NEVER_LIVE": {
            "forbidden_fields": [
                "BOUNDARY_TERMINAL_INSTALLATION_HIERARCHY",
                "DEADLINE_ELAPSED_PROOF",
                "NO_INSTALL_EVIDENCE",
                "PERMANENT_ISOLATION_EVIDENCE",
                "TRANSPORT_QUIESCENCE_EVIDENCE",
                "UNKNOWN_RETAINED_WORK_BOUND",
                *boundary_publication_artifacts,
            ],
            "required_fields": [
                (
                    "observer-grant-pending-never-live-closure-proof-type::"
                    "ObserverGrantPendingNeverLiveClosureProof"
                ),
                "EXACT_MEMBER_AND_PROJECTION",
                "ZERO_RELEASE_CAPABLE_ITEM_PROOF",
            ],
            "to_state": "AUTH_CLOSED_EXACT",
        },
        "TERMINAL_ACKED": {
            "forbidden_fields": [
                "DEADLINE_ELAPSED_PROOF",
                "NO_INSTALL_EVIDENCE",
                "PENDING_NEVER_LIVE_PROOF",
                "PERMANENT_ISOLATION_EVIDENCE",
                "TRANSPORT_QUIESCENCE_EVIDENCE",
                "UNKNOWN_RETAINED_WORK_BOUND",
            ],
            "required_fields": [
                "BOUNDARY_TERMINAL_INSTALLATION_HIERARCHY",
                "CANONICAL_RETAINED_ITEM_IDENTITY_COUNT_AND_ROOT_INVENTORY",
                "PASSING_CROSS_STORE_VERIFICATION",
                *boundary_publication_artifacts,
            ],
            "to_state": "AUTH_CLOSED_EXACT",
        },
    }
    transport_native_union_arms = {
        "EMERGENCY_COMPLETE_CLOSURE_TRANSPORT_QUIESCENT": {
            "forbidden_fields": [
                "BOUNDARY_TRANSPORT_QUIESCENCE_HIERARCHY",
                "NO_INSTALL_ZERO_ITEMS_EVIDENCE",
                "PENDING_NEVER_ZERO_ITEMS_PROOF",
                "PERMANENT_ISOLATION_ZERO_ITEMS_EVIDENCE",
            ],
            "required_fields": [
                (
                    "COMPLETE_EMERGENCY_ITEM_ATTEMPT_RETRY_AND_NO_PENDING_"
                    "TRANSPORT_PARTITION"
                ),
                "EMERGENCY_CLOSURE_MEMBER_HIERARCHY",
                *boundary_publication_artifacts,
            ],
        },
        "NO_INSTALL_ZERO_ITEMS": {
            "forbidden_fields": [
                "BOUNDARY_TRANSPORT_QUIESCENCE_HIERARCHY",
                "EMERGENCY_CLOSURE_MEMBER_HIERARCHY",
                "PENDING_NEVER_ZERO_ITEMS_PROOF",
                "PERMANENT_ISOLATION_ZERO_ITEMS_EVIDENCE",
                *boundary_publication_artifacts,
            ],
            "required_fields": [
                "EXACT_NO_INSTALL_EVIDENCE",
                "EXACT_ZERO_WORK_ROOTS",
            ],
        },
        "PERMANENT_ISOLATION_ZERO_ITEMS": {
            "forbidden_fields": [
                "BOUNDARY_TRANSPORT_QUIESCENCE_HIERARCHY",
                "EMERGENCY_CLOSURE_MEMBER_HIERARCHY",
                "NO_INSTALL_ZERO_ITEMS_EVIDENCE",
                "PENDING_NEVER_ZERO_ITEMS_PROOF",
                *boundary_publication_artifacts,
            ],
            "required_fields": [
                (
                    "COMPLETE_EXACT_ZERO_ITEM_ATTEMPT_RETRY_AND_PENDING_"
                    "TRANSPORT_PARTITION"
                ),
                "QUALIFIED_PERMANENT_ISOLATION_EVIDENCE",
            ],
        },
        "SERVER_TERMINAL_FROM_PENDING_NEVER_LIVE_ZERO_ITEMS": {
            "forbidden_fields": [
                "BOUNDARY_TRANSPORT_QUIESCENCE_HIERARCHY",
                "EMERGENCY_CLOSURE_MEMBER_HIERARCHY",
                "NO_INSTALL_ZERO_ITEMS_EVIDENCE",
                "PERMANENT_ISOLATION_ZERO_ITEMS_EVIDENCE",
                *boundary_publication_artifacts,
            ],
            "required_fields": [
                "EXACT_PENDING_NEVER_LIVE_PROOF",
                "ZERO_RELEASE_ITEM_IMPOSSIBILITY_PROOF",
            ],
        },
        "TERMINAL_ENTRY_TRANSPORT_QUIESCENT": {
            "forbidden_fields": [
                "EMERGENCY_CLOSURE_MEMBER_HIERARCHY",
                "NO_INSTALL_ZERO_ITEMS_EVIDENCE",
                "PENDING_NEVER_ZERO_ITEMS_PROOF",
                "PERMANENT_ISOLATION_ZERO_ITEMS_EVIDENCE",
            ],
            "required_fields": [
                "BOUNDARY_TRANSPORT_QUIESCENCE_HIERARCHY",
                (
                    "EXACT_ITEM_ATTEMPT_DISPOSITION_NO_RETRY_AND_NO_PENDING_"
                    "TRANSPORT_PARTITION"
                ),
                *boundary_publication_artifacts,
            ],
        },
    }
    return {
        "aggregate_output_derivation": {
            "AUTHORIZATION_CLOSED": (
                "EVERY_MEMBER_IS_AUTH_CLOSED_UNKNOWN_AUTH_CLOSED_EXACT_OR_"
                "TRANSPORT_QUIESCENT_AND_AT_LEAST_ONE_MEMBER_IS_NOT_"
                "TRANSPORT_QUIESCENT"
            ),
            "NO_COMPLETE_AGGREGATE": "AT_LEAST_ONE_MEMBER_IS_UNOBSERVED",
            "TRANSPORT_QUIESCENT": "EVERY_MEMBER_IS_TRANSPORT_QUIESCENT",
            "empty_member_set": (
                "TRANSPORT_QUIESCENT_ONLY_WITH_EXACT_COMPLETE_EMPTY_MEMBER_"
                "UNIVERSE_PROOF"
            ),
            "unknown_or_mismatch": "REJECT_WITHOUT_STATE_CHANGE",
        },
        "authority_effect": "NONE_AND_NO_ALLOW_POLICY_RESULT",
        "evidence_input": {
            "exact_empty_accepted_plan": {
                "affected_member_count": 0,
                "affected_member_set": "EXACT_EMPTY_CANONICAL_SET",
                "aggregate_output": "TRANSPORT_QUIESCENT",
                "canonical_empty_member_root": (
                    "DOMAIN_SEPARATED_CANONICAL_EMPTY_BOUNDARY_PLAN_MEMBER_ROOT"
                ),
                "forbidden_fields": [
                    "BOUNDARY_CLOSURE_DELIVERY_CAPSULE",
                    "BOUNDARY_CLOSURE_EVIDENCE_ENVELOPE",
                    "BOUNDARY_CLOSURE_FAMILY_MANIFEST",
                    "BOUNDARY_CLOSURE_PRODUCER_COMPLETION_MANIFEST",
                    "BOUNDARY_CLOSURE_SECURITY_VERIFICATION",
                    "DEADLINE_ELAPSED_MEMBER_EVIDENCE",
                    "MEMBER_EVIDENCE_BIJECTION",
                    "PERMANENT_ISOLATION_MEMBER_EVIDENCE",
                    "TRANSPORT_QUIESCENCE_MEMBER_EVIDENCE",
                ],
                "installed_head": (
                    "ONE_CANONICAL_VERSION_ONE_TERMINAL_EMPTY_HEAD_FROM_TYPED_"
                    "NEVER_AGGREGATED_EMPTY_HEAD"
                ),
                "proof": OBSERVER_GRANT_CLOSURE_AGGREGATION_EMPTY_UNIVERSE_PROOF,
                "proof_binds": (
                    "AUTHENTICATED_ACCEPTED_RESULT_RECEIPT_AND_COMMITMENT_FULL_"
                    "GRANT_INSTALLATION_IDENTITY_IMMUTABLE_BOUNDARY_PLAN_DOMAIN_"
                    "SEPARATED_EMPTY_MEMBER_ROOT_MEMBER_COUNT_ZERO_CURRENT_TARGET_"
                    "HISTORY_AND_TYPED_NEVER_AGGREGATED_EMPTY_HEAD"
                ),
                "receipt_binding": (
                    "DISTRIBUTED_AUTHORIZATION_CLOSURE_AND_TRANSPORT_QUIESCENCE_"
                    "RECEIPTS_BIND_EXACT_EMPTY_UNIVERSE_DISCRIMINANT_PROOF_DIGEST_"
                    "AND_DOMAIN_SEPARATED_EMPTY_MEMBER_ROOT"
                ),
                "retry": (
                    "ONLY_THE_ORIGINAL_DERIVED_OPERATION_RETURNS_THE_EXACT_RETAINED_"
                    "EMPTY_HEAD_RECEIPTS_AND_PUBLICATION_BUNDLE"
                ),
            },
            "member_advance_batch": {
                "affected_member_count": "ONE_OR_MORE_BOUNDED",
                "bijection": (
                    OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_EVIDENCE_BIJECTION
                ),
                "bijection_member_fields": [
                    "LATTICE_EDGE",
                    "MEMBER_KEY",
                    "NATIVE_EVIDENCE_DIGEST",
                    "NATIVE_EVIDENCE_UNION_TAG",
                    "PRIOR_REFINEMENT_ANCESTRY",
                ],
                "bijection_root": (
                    "DOMAIN_SEPARATED_CANONICAL_AFFECTED_MEMBER_TO_LATTICE_EDGE_"
                    "NATIVE_UNION_TAG_EVIDENCE_DIGEST_AND_PRIOR_REFINEMENT_ANCESTRY_"
                    "BIJECTION_ROOT"
                ),
                "bijection_rule": (
                    "EXACTLY_ONE_SAME_KEY_NATIVE_EVIDENCE_UNION_MEMBER_PER_AFFECTED_"
                    "MEMBER_AND_NO_UNAFFECTED_MEMBER"
                ),
                "partition_rule": (
                    "EVERY_AFFECTED_MEMBER_ADVANCES_EXACTLY_ONE_LISTED_LATTICE_EDGE_"
                    "AND_EVERY_UNLISTED_MEMBER_IS_BYTE_PRESERVED"
                ),
                "per_member_authorization_origin": {
                    "AUTH_CLOSED_EXACT": [
                        (
                            "BOUNDARY_PERMANENTLY_ISOLATED_WITH_COMPLETE_EXACT_"
                            "WORK_PARTITION"
                        ),
                        "NO_INSTALL_ZERO_WORK_PROVED",
                        "SERVER_TERMINAL_FROM_PENDING_NEVER_LIVE",
                        "TERMINAL_ACKED",
                    ],
                    "AUTH_CLOSED_UNKNOWN": [
                        ("BOUNDARY_PERMANENTLY_ISOLATED_WITH_UNKNOWN_RETAINED_WORK"),
                        ("DEADLINE_ELAPSED_UNACKNOWLEDGED_WITH_UNKNOWN_RETAINED_WORK"),
                    ],
                    "artifact": (
                        "observer-grant-distributed-authorization-closure-member-"
                        "evidence-type::"
                        "ObserverGrantDistributedAuthorizationClosureMemberEvidence"
                    ),
                    "native_union_arms": authorization_native_union_arms,
                },
                "per_member_transport_origin": {
                    "artifact": (
                        "observer-grant-transport-quiescence-member-evidence-type::"
                        "ObserverGrantTransportQuiescenceMemberEvidence"
                    ),
                    "exact_origins": [
                        "EMERGENCY_COMPLETE_CLOSURE_TRANSPORT_QUIESCENT",
                        "NO_INSTALL_ZERO_ITEMS",
                        "PERMANENT_ISOLATION_ZERO_ITEMS",
                        "SERVER_TERMINAL_FROM_PENDING_NEVER_LIVE_ZERO_ITEMS",
                        "TERMINAL_ENTRY_TRANSPORT_QUIESCENT",
                    ],
                    "native_union_arms": transport_native_union_arms,
                    "rule": (
                        "EXACT_SAME_MEMBER_AUTHORIZATION_MEMBER_DIGEST_AND_FULL_"
                        "REFINEMENT_ANCESTRY_INCLUDING_ANY_PRIOR_UNKNOWN_EVIDENCE_"
                        "PLUS_COMPLETE_ZERO_WORK_OR_TRANSPORT_DISPOSITION_PROOF"
                    ),
                },
                "refinement": (
                    "AUTH_CLOSED_UNKNOWN_TO_AUTH_CLOSED_EXACT_RETAINS_THE_PRIOR_"
                    "UNKNOWN_EVIDENCE_CLASS_DIGEST_RECEIPT_OR_PROOF_AND_THE_LATER_"
                    "EXACT_EVIDENCE_CLASS_DIGEST_RECEIPT_OR_PROOF"
                ),
                "shared_publication_hierarchy": (
                    "A_SHARED_FAMILY_OR_COMPLETION_MANIFEST_IS_REFERENCED_BY_"
                    "MULTIPLE_MEMBER_RECORDS_ONLY_THROUGH_EACH_EXACT_ENVELOPE_"
                    "IDENTITY_AND_BOTH_SCOPED_MEMBERSHIP_PROOFS_NEVER_AS_A_ONE_TO_"
                    "ONE_MANIFEST_PER_MEMBER"
                ),
                "unknown_union_tag_extra_arm_field_or_missing_forbidden_field": (
                    "REJECT_WITHOUT_STATE_CHANGE"
                ),
            },
            "partition_cardinality_by_input": {
                "EXACT_EMPTY_ACCEPTED_PLAN": (
                    "ALL_FOUR_MEMBER_PARTITIONS_ARE_EXPLICITLY_EMPTY_AND_MEMBER_"
                    "WRITE_CARDINALITY_IS_ZERO"
                ),
                "MEMBER_ADVANCE_BATCH": (
                    "AFFECTED_MEMBER_COUNT_IS_ONE_OR_MORE_AND_EVERY_AFFECTED_"
                    "MEMBER_APPEARS_IN_EXACTLY_ONE_PARTITION"
                ),
            },
            "type": OBSERVER_GRANT_CLOSURE_AGGREGATION_EVIDENCE_INPUT,
            "union": [
                "EXACT_EMPTY_ACCEPTED_PLAN",
                "MEMBER_ADVANCE_BATCH",
            ],
            "unknown_default_mixed_or_cross_member": "REJECT_WITHOUT_STATE_CHANGE",
        },
        "head": {
            "content": (
                "EXACT_CANONICAL_SORTED_MEMBER_KEY_STATE_VERSION_SET_PRIOR_"
                "HEAD_DIGEST_AND_AGGREGATE_OUTPUT"
            ),
            "empty_universe_genesis": (
                "ONLY_FROM_TYPED_NEVER_AGGREGATED_EMPTY_HEAD_TO_ONE_CANONICAL_"
                "VERSION_ONE_TRANSPORT_QUIESCENT_EMPTY_HEAD_THAT_BINDS_THE_EMPTY_"
                "PROOF_DISCRIMINANT_AND_DOMAIN_SEPARATED_EMPTY_MEMBER_ROOT"
            ),
            "empty_universe_successor_or_second_operation": (
                "FORBIDDEN_EXCEPT_EXACT_RETAINED_REPLAY_OF_THE_ORIGINAL_DERIVED_"
                "OPERATION"
            ),
            "prior": "EXACT_EXISTING_HEAD_OR_TYPED_NEVER_AGGREGATED_EMPTY_HEAD",
            "type": OBSERVER_GRANT_CLOSURE_AGGREGATION_HEAD,
            "update": (
                "ONE_ATOMIC_CAS_FROM_EXACT_PRIOR_HEAD_TO_CONTENT_ADDRESSED_"
                "SUCCESSOR_HEAD"
            ),
        },
        "idempotency": {
            "caller_supplied_operation_id": "FORBIDDEN",
            "crash_after_cas_before_sidecars": (
                "COMPLETE_THE_ONE_DETERMINISTIC_DURABLE_BUNDLE_WITHOUT_"
                "REPEATING_THE_SEMANTIC_MUTATION_OR_EXPOSING_PARTIAL_STATE"
            ),
            "crash_before_cas": "PRESERVE_THE_PRIOR_DURABLE_BUNDLE",
            "derivation": (
                "DOMAIN_SEPARATED_CANONICAL_DIGEST_OF_EVERY_LISTED_COORDINATE_"
                "WITH_NO_CALLER_SELECTED_NONCE_OR_FRESH_ID"
            ),
            "evidence_input_commitment_root": (
                "MEMBER_ADVANCE_BATCH_USES_THE_DOMAIN_SEPARATED_MEMBER_EVIDENCE_"
                "BIJECTION_ROOT_AND_EXACT_EMPTY_ACCEPTED_PLAN_USES_THE_DOMAIN_"
                "SEPARATED_EMPTY_PROOF_COMMITMENT_ROOT"
            ),
            "key": OBSERVER_GRANT_CLOSURE_AGGREGATION_OPERATION_KEY,
            "key_coordinates": [
                "AUTHORITY_TRANSACTION_DOMAIN_KEY",
                "SERVER_AUTHORITY_REALM",
                "SOURCE_SESSION_KIND",
                "SOURCE_LOGICAL_SESSION_ID",
                "AUTHENTICATED_REQUESTER_PRINCIPAL",
                "EXPECTED_TARGET_HISTORY_HEAD_DIGEST",
                "EXPECTED_TARGET_HISTORY_ENTRY_DIGEST",
                "TERMINAL_DECISION_DIGEST",
                "OBSERVER_GRANT_REGISTRY_INCARNATION",
                "OBSERVER_GRANT_ISSUANCE_SEQUENCE",
                "OBSERVER_GRANT_DIGEST",
                "ACCEPTED_RESULT_COMMITMENT_DIGEST",
                "ACCEPTED_RESULT_BOUNDARY_PLAN_MEMBER_ROOT",
                "EVIDENCE_INPUT_COMMITMENT_ROOT",
                "PRIOR_AGGREGATION_HEAD_DIGEST",
                "PRIOR_AGGREGATION_MEMBER_STATE_ROOT",
                "NEXT_AGGREGATION_MEMBER_STATE_ROOT",
                "AGGREGATE_OUTPUT_CLASS",
                "PRE_CAS_SEMANTIC_INPUT_DIGEST",
            ],
            "pre_cas_semantic_input_digest": (
                "DOMAIN_SEPARATED_CANONICAL_DIGEST_OF_THE_COMPLETE_FACT_SEMANTIC_"
                "INPUT_INCLUDING_THE_CLOSED_EVIDENCE_INPUT_COMMITMENT_BUT_"
                "EXCLUDING_THE_OPERATION_KEY_AND_EVERY_CANDIDATE_RECEIPT_OR_SIDECAR"
            ),
            "reply_loss": (
                "RETURN_THE_EXACT_RETAINED_RECEIPT_AND_COMPLETE_PUBLICATION_BUNDLE"
            ),
            "same_key_changed_prior_head_member_set_event_bytes_or_cause": ("REJECT"),
        },
        "member": {
            "domain": OBSERVER_GRANT_CLOSURE_AGGREGATION_DOMAIN,
            "initial_state": "UNOBSERVED",
            "key": OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_KEY,
            "lattice_edges": [
                {
                    "entry_effect": "MUTATE",
                    "from_state": "UNOBSERVED",
                    "to_state": "AUTH_CLOSED_UNKNOWN",
                },
                {
                    "entry_effect": "MUTATE",
                    "from_state": "UNOBSERVED",
                    "to_state": "AUTH_CLOSED_EXACT",
                },
                {
                    "entry_effect": "MUTATE",
                    "from_state": "AUTH_CLOSED_UNKNOWN",
                    "to_state": "AUTH_CLOSED_EXACT",
                },
                {
                    "entry_effect": "TOMBSTONE",
                    "from_state": "AUTH_CLOSED_EXACT",
                    "to_state": "TRANSPORT_QUIESCENT",
                },
            ],
            "states": [
                "AUTH_CLOSED_EXACT",
                "AUTH_CLOSED_UNKNOWN",
                "TRANSPORT_QUIESCENT",
                "UNOBSERVED",
            ],
            "terminal_states": ["TRANSPORT_QUIESCENT"],
            "type": OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_STATE,
            "unknown_default_or_unlisted_edge": "REJECT_WITHOUT_STATE_CHANGE",
        },
        "member_universe": {
            "authority": (
                "EXACT_IMMUTABLE_ACCEPTED_RESULT_BOUNDARY_INSTALLATION_PLAN_"
                "MEMBER_ROOT_COUNT_AND_KEY_DIGEST_BIJECTION"
            ),
            "current_state_source": (
                "TARGET_HISTORY_SUPPLIES_ONLY_THE_CURRENT_STATE_FOR_EACH_"
                "IMMUTABLE_PLAN_MEMBER"
            ),
            "mutable_source_index_effect": (
                "CANNOT_ADD_REMOVE_REKEY_OR_REDEFINE_MEMBERS"
            ),
            "proof": (
                "EXACT_ACCEPTED_RESULT_COMMITMENT_TO_BOUNDARY_PLAN_TO_MEMBER_ROOT_"
                "COUNT_AND_COMPLETE_MEMBER_KEY_DIGEST_BIJECTION"
            ),
        },
        "unknown_missing_duplicate_cross_member_or_regression": (
            "REJECT_WITHOUT_STATE_CHANGE"
        ),
    }


def _validate_observer_grant_closure_aggregation_contract(
    data: dict[str, Any],
) -> None:
    """Require the closed member lattice and its all-or-none result hierarchy."""

    selector = next(
        (
            item
            for item in data["selectors"]
            if item["selector_id"] == "OBSERVER_ATTACHMENT_TARGET_HISTORY"
        ),
        None,
    )
    require(
        selector is not None,
        "missing OBSERVER_ATTACHMENT_TARGET_HISTORY selector",
    )
    require_exact(
        data["observer_grant_request_target_profile"].get(
            "closure_aggregation_contract"
        ),
        _observer_grant_closure_aggregation_profile_contract(),
        "observer grant closure-aggregation profile contract",
    )
    require(
        {
            OBSERVER_GRANT_CLOSURE_AGGREGATION_EMPTY_UNIVERSE_PROOF,
            OBSERVER_GRANT_CLOSURE_AGGREGATION_EVIDENCE_INPUT,
            OBSERVER_GRANT_CLOSURE_AGGREGATION_HEAD,
            OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_EVIDENCE_BIJECTION,
            OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_KEY,
            OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_STATE,
            OBSERVER_GRANT_CLOSURE_AGGREGATION_OPERATION_KEY,
            (
                "observer-grant-distributed-authorization-closure-member-"
                "evidence-type::"
                "ObserverGrantDistributedAuthorizationClosureMemberEvidence"
            ),
            (
                "observer-grant-transport-quiescence-member-evidence-type::"
                "ObserverGrantTransportQuiescenceMemberEvidence"
            ),
            (
                "trusted-delivery-boundary-grant-no-install-evidence-type::"
                "TrustedDeliveryBoundaryGrantNoInstallEvidence"
            ),
            (
                "observer-grant-pending-never-live-closure-proof-type::"
                "ObserverGrantPendingNeverLiveClosureProof"
            ),
        }.issubset(set(data["artifacts"])),
        "observer closure-aggregation profile references unregistered artifacts",
    )
    domain = next(
        (
            item
            for item in selector["state_domains"]
            if item["state_domain"] == OBSERVER_GRANT_CLOSURE_AGGREGATION_DOMAIN
        ),
        None,
    )
    require(
        domain is not None,
        (
            "OBSERVER_ATTACHMENT_TARGET_HISTORY: missing "
            f"{OBSERVER_GRANT_CLOSURE_AGGREGATION_DOMAIN} state domain"
        ),
    )
    require_exact(
        set(domain["states"]),
        {
            "AUTH_CLOSED_EXACT",
            "AUTH_CLOSED_UNKNOWN",
            "TRANSPORT_QUIESCENT",
            "UNOBSERVED",
        },
        "observer closure-aggregation member state union",
    )
    require_exact(
        domain["initial_state"],
        "UNOBSERVED",
        "observer closure-aggregation initial member state",
    )
    require_exact(
        domain["terminal_states"],
        ["TRANSPORT_QUIESCENT"],
        "observer closure-aggregation terminal member state",
    )
    require_exact(
        domain["terminality"],
        "ALL_REACH_TERMINAL",
        "observer closure-aggregation terminality",
    )
    require_exact(
        domain["key_type"],
        OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_KEY,
        "observer closure-aggregation member key",
    )
    require_exact(
        domain["key_mode"],
        "EXACT_KEY_OR_CANONICAL_PARTITION",
        "observer closure-aggregation member key mode",
    )
    require_exact(
        domain["scope"],
        "KEYED_MAP_ENTRY",
        "observer closure-aggregation member scope",
    )
    require_exact(
        domain["owner_selector_id"],
        "OBSERVER_ATTACHMENT_TARGET_HISTORY",
        "observer closure-aggregation owner",
    )

    event = next(
        (
            item
            for item in selector["events"]
            if item["event_id"] == OBSERVER_GRANT_CLOSURE_AGGREGATION_EVENT
        ),
        None,
    )
    require(
        event is not None,
        (
            "OBSERVER_ATTACHMENT_TARGET_HISTORY: missing "
            f"{OBSERVER_GRANT_CLOSURE_AGGREGATION_EVENT}"
        ),
    )
    require_exact(
        event["operation_scope"],
        "BOUNDED_KEY_SET",
        "observer closure-aggregation operation scope",
    )
    require_exact(
        event["transition_kind"],
        (
            "observer-attachment-target-history-transition-kind::"
            "ADVANCE_OBSERVER_GRANT_CLOSURE_AGGREGATION"
        ),
        "observer closure-aggregation transition kind",
    )
    require_exact(
        event["transition_kind_state_domain"],
        "ROOT",
        "observer closure-aggregation transition-kind state domain",
    )
    member_resource = (
        "OBSERVER_ATTACHMENT_TARGET_HISTORY.STATE_DOMAIN."
        f"{OBSERVER_GRANT_CLOSURE_AGGREGATION_DOMAIN}"
    )
    member_write_effects = [
        effect
        for effect in event["common_case_effects"]
        if effect["resource"] == member_resource and effect["action"] == "WRITE"
    ]
    require_exact(
        len(member_write_effects),
        1,
        "observer closure-aggregation member write effect count",
    )
    require_exact(
        member_write_effects[0]["cardinality"],
        "ZERO_OR_MORE_BOUNDED_KEYS",
        "observer closure-aggregation member write cardinality",
    )
    expected_common_effects = {
        (
            "WRITE",
            "ROOT",
            (
                "OBSERVER_ATTACHMENT_TARGET_HISTORY."
                "OBSERVER_ATTACHMENT_TARGET_HISTORY_REGISTRY_HEAD"
            ),
        ),
        (
            "WRITE",
            "EXACT_ONE_KEY",
            "OBSERVER_ATTACHMENT_TARGET_HISTORY.OPERATION_COMMITMENT_INDEX",
        ),
        (
            "WRITE",
            "EXACT_ONE_KEY",
            (
                "OBSERVER_ATTACHMENT_TARGET_HISTORY."
                "OBSERVER_GRANT_CLOSURE_AGGREGATION_HEAD"
            ),
        ),
        (
            "WRITE",
            "ZERO_OR_MORE_BOUNDED_KEYS",
            member_resource,
        ),
        (
            "CONDITIONAL_COMPARE",
            "EXACTLY_ONE",
            "SECURITY_AUTHORITY.SELECTOR",
        ),
    }
    require_exact(
        {
            (effect["action"], effect["cardinality"], effect["resource"])
            for effect in event["common_case_effects"]
        },
        expected_common_effects,
        "observer closure-aggregation exact common effects",
    )
    require_exact(
        set(event["common_case_mutates"]),
        {
            (
                "OBSERVER_ATTACHMENT_TARGET_HISTORY."
                "OBSERVER_ATTACHMENT_TARGET_HISTORY_REGISTRY_HEAD"
            ),
            (
                "OBSERVER_ATTACHMENT_TARGET_HISTORY."
                "OBSERVER_GRANT_CLOSURE_AGGREGATION_HEAD"
            ),
            "OBSERVER_ATTACHMENT_TARGET_HISTORY.OPERATION_COMMITMENT_INDEX",
            member_resource,
        },
        "observer closure-aggregation exact mutation inventory",
    )

    require_exact(
        len(event["partition_effects"]),
        1,
        "observer closure-aggregation partition count",
    )
    partition = event["partition_effects"][0]
    require_exact(
        partition["partition_id"],
        "P001",
        "observer closure-aggregation partition identity",
    )
    require_exact(
        partition["state_domain"],
        OBSERVER_GRANT_CLOSURE_AGGREGATION_DOMAIN,
        "observer closure-aggregation partition domain",
    )
    require_exact(
        partition["key_type"],
        OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_KEY,
        "observer closure-aggregation partition key",
    )
    require_exact(
        partition["coverage"],
        "EXACT_DISJOINT_COMPLETE_KEY_PARTITION",
        "observer closure-aggregation partition coverage",
    )
    require_exact(
        partition["bijection"],
        "EXACTLY_ONE_BRANCH_AND_OUTCOME_PER_AFFECTED_MEMBER",
        "observer closure-aggregation partition bijection",
    )
    require_exact(
        partition["empty_partitions"],
        "PERMITTED_AND_EXPLICIT",
        "observer closure-aggregation empty partition",
    )
    require_exact(
        partition["preserve_unlisted_keys"],
        True,
        "observer closure-aggregation sibling preservation",
    )
    require_exact(
        partition["cross_branch_constraints"],
        (
            "UNKNOWN_ONLY_FOR_DEADLINE_OR_ISOLATION_UNKNOWN_WORK_EXACT_ONLY_FOR_"
            "PROVED_TERMINAL_BRANCH_AND_QUIESCENT_ONLY_FROM_SAME_MEMBER_EXACT_"
            "AUTHORIZATION_CLOSURE"
        ),
        "observer closure-aggregation cross-branch constraints",
    )
    require_exact(
        partition["inventory_semantics"],
        (
            "MEMBER_ADVANCE_BATCH_HAS_ONE_OR_MORE_EXACT_CANONICAL_AFFECTED_"
            "MEMBERS_WITH_ONE_LATTICE_EDGE_AND_CANDIDATE_PER_MEMBER_EXACT_EMPTY_"
            "ACCEPTED_PLAN_HAS_ZERO_MEMBER_WRITES_AND_ALL_FOUR_PARTITIONS_"
            "EXPLICITLY_EMPTY"
        ),
        "observer closure-aggregation partition input cardinality",
    )
    require_exact(
        partition["missing_extra_duplicate_or_nonterminal"],
        (
            "REJECT_MISSING_EXTRA_DUPLICATE_REGRESSING_UNKNOWN_TO_QUIESCENT_OR_"
            "CROSS_MEMBER_EVIDENCE"
        ),
        "observer closure-aggregation partition rejection rule",
    )
    require_exact(
        partition["unrelated_entries"],
        "BYTE_PRESERVED",
        "observer closure-aggregation unrelated member preservation",
    )
    branch_ids = [branch["branch_id"] for branch in partition["branches"]]
    require_unique(branch_ids, "observer closure-aggregation branch identities")
    actual_branches = {
        branch["branch_id"]: (branch["from_state"], branch["to_state"])
        for branch in partition["branches"]
    }
    require_exact(
        actual_branches,
        OBSERVER_GRANT_CLOSURE_AGGREGATION_LATTICE_BRANCHES,
        "observer closure-aggregation closed lattice",
    )
    for branch in partition["branches"]:
        branch_label = f"observer closure-aggregation branch {branch['branch_id']}"
        require_exact(
            branch["cardinality"],
            "ZERO_OR_MORE_BOUNDED_KEYS",
            f"{branch_label} cardinality",
        )
        require_exact(
            branch["entry_effect"],
            OBSERVER_GRANT_CLOSURE_AGGREGATION_BRANCH_EFFECTS[branch["branch_id"]],
            f"{branch_label} effect",
        )
        require_exact(branch["key_mode"], "PARTITION", f"{branch_label} key mode")
        require_exact(
            branch["key_partition"],
            f"CANONICAL_{branch['branch_id']}_MEMBER_SET",
            f"{branch_label} exact key partition",
        )
        require_exact(
            branch["key_ref"],
            OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_KEY,
            f"{branch_label} key",
        )
        require_exact(
            branch["version_effect"],
            "INCREMENT_EXACTLY_ONE",
            f"{branch_label} version effect",
        )

    edge_by_id = {edge["edge_id"]: edge for edge in selector["state_edge_catalog"]}
    scalar_aggregation_edges = [
        edge
        for edge in edge_by_id.values()
        if edge["state_domain"] == OBSERVER_GRANT_CLOSURE_AGGREGATION_DOMAIN
    ]
    require(
        not scalar_aggregation_edges,
        (
            "observer closure aggregation must execute its complete member "
            "partition rather than expose unreferenced scalar lattice edges"
        ),
    )

    variants = event["decision_model"]["evidence_variant_definitions"]
    variant_ids = [variant["evidence_variant_id"] for variant in variants]
    require_unique(
        variant_ids,
        "observer closure-aggregation evidence variants",
    )
    variant_by_id = {variant["evidence_variant_id"]: variant for variant in variants}
    require_exact(
        set(variant_by_id),
        set(OBSERVER_GRANT_CLOSURE_AGGREGATION_VARIANTS),
        "observer closure-aggregation closed evidence variants",
    )
    common_required = set(event["decision_model"]["common_required_fields"])
    require_exact(
        common_required,
        {
            "PRE_CAS_CONTENT.authenticated_evidence",
            "PRE_CAS_CONTENT.semantic_case",
            "PRE_CAS_CONTENT.typed_fact_validation_receipt",
        },
        "observer closure-aggregation common evidence fields",
    )
    common_variant_fields = {
        OBSERVER_GRANT_CLOSURE_AGGREGATION_EVIDENCE_INPUT_FIELD,
        OBSERVER_GRANT_CLOSURE_AGGREGATION_AUTHORITY_EFFECT_FIELD,
        OBSERVER_GRANT_CLOSURE_AGGREGATION_MARKER_EFFECT_FIELD,
        OBSERVER_GRANT_CLOSURE_AGGREGATION_OUTPUT_FIELD,
    }
    for variant_id, variant in variant_by_id.items():
        variant_label = f"observer closure-aggregation variant {variant_id}"
        evidence_input_kind, aggregate_output = (
            OBSERVER_GRANT_CLOSURE_AGGREGATION_VARIANTS[variant_id]
        )
        empty_universe = evidence_input_kind == "EXACT_EMPTY_ACCEPTED_PLAN"
        branch_field = (
            OBSERVER_GRANT_CLOSURE_AGGREGATION_EMPTY_UNIVERSE_PROOF_FIELD
            if empty_universe
            else OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_EVIDENCE_BIJECTION_FIELD
        )
        opposite_branch_field = (
            OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_EVIDENCE_BIJECTION_FIELD
            if empty_universe
            else OBSERVER_GRANT_CLOSURE_AGGREGATION_EMPTY_UNIVERSE_PROOF_FIELD
        )
        require_exact(
            set(variant["required_fields"]),
            common_variant_fields | {branch_field},
            f"{variant_label}: exact required field set",
        )
        expected_forbidden = {
            opposite_branch_field,
            CROSS_STORE_PRODUCER_COMPLETION_MANIFEST_FIELD,
            CROSS_STORE_PROTECTED_OUTPUT_DELIVERY_CAPSULE_FIELD,
            OBSERVER_GRANT_REQUEST_VERIFICATION_FIELD,
            TRUSTED_DELIVERY_BOUNDARY_CLOSURE_ENVELOPE_FIELD,
            TRUSTED_DELIVERY_BOUNDARY_CLOSURE_MANIFEST_FIELD,
        }
        if empty_universe:
            expected_forbidden |= {
                "PRE_CAS_CONTENT.observer_grant_deadline_elapsed_member_evidence",
                "PRE_CAS_CONTENT.observer_grant_permanent_isolation_member_evidence",
                "PRE_CAS_CONTENT.observer_grant_transport_quiescence_member_evidence",
            }
        require_exact(
            set(variant["forbidden_fields"]),
            expected_forbidden,
            f"{variant_label}: exact branch-specific forbidden fields",
        )
        conditions = variant["truth_conditions"]
        for field, expected_value in (
            (OBSERVER_GRANT_CLOSURE_AGGREGATION_OUTPUT_FIELD, aggregate_output),
            (
                OBSERVER_GRANT_CLOSURE_AGGREGATION_AUTHORITY_EFFECT_FIELD,
                "NO_AUTHORITY_OR_ALLOW",
            ),
            (
                OBSERVER_GRANT_CLOSURE_AGGREGATION_MARKER_EFFECT_FIELD,
                "PRESERVE_OR_TYPED_INAPPLICABLE_NO_WRITE",
            ),
        ):
            require(
                any(
                    condition["field"] == field
                    and condition["operator"] == "EQUALS"
                    and condition["value"] == expected_value
                    for condition in conditions
                ),
                f"{variant_label}: {field} lacks exact closed value",
            )
        require(
            any(
                condition["field"]
                == OBSERVER_GRANT_CLOSURE_AGGREGATION_EVIDENCE_INPUT_FIELD
                and condition["operator"] == "CLOSED_UNION_VARIANT_EQUALS"
                and condition["value"] == evidence_input_kind
                for condition in conditions
            ),
            f"{variant_label}: evidence-input union arm is not exact",
        )
        branch_operator = (
            "BINDS_AUTHENTICATED_ACCEPTED_RESULT_IMMUTABLE_DOMAIN_SEPARATED_"
            "EMPTY_PLAN_ROOT_COUNT_ZERO_TYPED_NEVER_AGGREGATED_EMPTY_HEAD_AND_"
            "CANONICAL_VERSION_ONE_TERMINAL_EMPTY_SUCCESSOR_WITH_NO_MEMBER_EVIDENCE"
            if empty_universe
            else OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_BIJECTION_OPERATOR
        )
        require(
            any(
                condition["field"] == branch_field
                and condition["operator"] == branch_operator
                and condition["value"] is True
                for condition in conditions
            ),
            f"{variant_label}: branch evidence truth is incomplete",
        )
        require(
            any(
                condition["field"] == "PRE_CAS_CONTENT.typed_fact_validation_receipt"
                and condition["operator"]
                == "BINDS_SIGNATURE_SCOPE_SCHEMA_DIGEST_AND_DERIVED_INPUT_AXES"
                and condition["value"]
                == (
                    "OBSERVER_ATTACHMENT_TARGET_HISTORY."
                    "ADVANCE_OBSERVER_GRANT_CLOSURE_AGGREGATION"
                )
                for condition in conditions
            ),
            f"{variant_label}: typed fact validation scope is missing",
        )

    target_entry_states = {
        "CURRENT_SOURCE_GENERATION",
        "SOURCE_AUTHORIZATION_RETIRED_PENDING_PARENT_FINALIZATION",
        "SOURCE_GENERATION_FINALIZED_PENDING_CHECKPOINT_PUBLICATION",
    }
    cases = event["transition_cases"]
    case_ids = [case["semantic_case_id"] for case in cases]
    require_unique(case_ids, "observer closure-aggregation semantic cases")
    actual_case_product: set[tuple[str, str]] = set()
    case_ids_by_variant: dict[str, set[str]] = {
        variant_id: set() for variant_id in OBSERVER_GRANT_CLOSURE_AGGREGATION_VARIANTS
    }
    for transition_case in cases:
        case_id = transition_case["semantic_case_id"]
        variant_id = transition_case["evidence_variant_id"]
        require(
            variant_id in variant_by_id,
            f"observer closure-aggregation case {case_id}: unknown variant",
        )
        require_exact(
            transition_case["case_contract"]["partition_effect_refs"],
            ["P001"],
            f"observer closure-aggregation case {case_id} partition",
        )
        edges = [
            edge_by_id[edge_ref] for edge_ref in transition_case["state_edge_refs"]
        ]
        edges_by_domain: dict[str, list[dict[str, Any]]] = {}
        for edge in edges:
            edges_by_domain.setdefault(edge["state_domain"], []).append(edge)
        require_exact(
            set(edges_by_domain),
            {"ROOT", "TARGET_HISTORY_ENTRY"},
            f"observer closure-aggregation case {case_id} scalar domains",
        )
        require_exact(
            len(edges_by_domain["ROOT"]),
            1,
            f"observer closure-aggregation case {case_id} root edge count",
        )
        require_exact(
            (
                edges_by_domain["ROOT"][0]["from_state"],
                edges_by_domain["ROOT"][0]["to_state"],
            ),
            ("OPEN_TARGET_HISTORY", "OPEN_TARGET_HISTORY"),
            f"observer closure-aggregation case {case_id} root edge",
        )
        require_exact(
            len(edges_by_domain["TARGET_HISTORY_ENTRY"]),
            1,
            f"observer closure-aggregation case {case_id} target edge count",
        )
        target_edge = edges_by_domain["TARGET_HISTORY_ENTRY"][0]
        require(
            target_edge["from_state"] in target_entry_states
            and target_edge["to_state"] == target_edge["from_state"],
            f"observer closure-aggregation case {case_id}: invalid target edge",
        )
        actual_case_product.add((target_edge["from_state"], variant_id))
        case_ids_by_variant[variant_id].add(case_id)
    require_exact(
        actual_case_product,
        {
            (target_state, variant_id)
            for target_state in target_entry_states
            for variant_id in OBSERVER_GRANT_CLOSURE_AGGREGATION_VARIANTS
        },
        "observer closure-aggregation target/evidence-variant case product",
    )
    require_exact(
        len(cases),
        12,
        "observer closure-aggregation semantic-case count",
    )
    require_exact(
        set(partition["applies_to_semantic_case_ids"]),
        set(case_ids),
        "observer closure-aggregation partition applicability",
    )
    empty_universe_case_ids = case_ids_by_variant["TRANSPORT_QUIESCENT_EMPTY_UNIVERSE"]
    member_batch_case_ids = set(case_ids) - empty_universe_case_ids

    authority_contract = event.get("authority_transaction_contract")
    require(
        authority_contract is not None,
        "observer closure aggregation lacks an authority transaction",
    )
    participant_roles = {
        "AUTHORITY_TRANSACTION_DOMAIN_STATE",
        "LOCAL_SECURITY_ENFORCEMENT",
        "LOGICAL_SESSION_LINEAGE",
        "OBSERVER_TARGET_HISTORY",
    }
    write_roles = {
        "AUTHORITY_TRANSACTION_DOMAIN_STATE",
        "OBSERVER_TARGET_HISTORY",
    }
    require_exact(
        set(authority_contract["write_roles"]),
        write_roles,
        "observer closure-aggregation write roles",
    )
    role_variants = authority_contract["participant_role_variants"]
    require_exact(
        len(role_variants),
        1,
        "observer closure-aggregation participant-role variant count",
    )
    require_exact(
        set(role_variants[0]["participant_roles"]),
        participant_roles,
        "observer closure-aggregation participant roles",
    )
    require_exact(
        set(role_variants[0]["write_roles"]),
        write_roles,
        "observer closure-aggregation variant write roles",
    )

    required_consumes = {
        (
            "installed-observer-attachment-target-history-selector-identity::"
            "InstalledObserverAttachmentTargetHistorySelector",
            "EXPECTED_PRIOR_SELECTOR",
        ),
        (
            "observer-grant-closure-aggregation-fact-type::"
            "ObserverGrantClosureAggregationFact",
            "PRE_CAS_FACT_OR_CONTENT",
        ),
        (
            OBSERVER_GRANT_CLOSURE_AGGREGATION_EVIDENCE_INPUT,
            "CLOSED_TYPED_AGGREGATION_EVIDENCE_INPUT",
        ),
        (
            OBSERVER_GRANT_CLOSURE_AGGREGATION_EMPTY_UNIVERSE_PROOF,
            "EXACT_EMPTY_ACCEPTED_PLAN_PROOF",
        ),
        (
            OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_EVIDENCE_BIJECTION,
            "EXACT_AFFECTED_MEMBER_NATIVE_EVIDENCE_BIJECTION",
        ),
        (
            (
                "observer-grant-distributed-authorization-closure-member-"
                "evidence-type::"
                "ObserverGrantDistributedAuthorizationClosureMemberEvidence"
            ),
            "PER_MEMBER_AUTHORIZATION_CLOSURE_NATIVE_EVIDENCE",
        ),
        (
            (
                "observer-grant-transport-quiescence-member-evidence-type::"
                "ObserverGrantTransportQuiescenceMemberEvidence"
            ),
            "PER_MEMBER_TRANSPORT_QUIESCENCE_NATIVE_EVIDENCE",
        ),
        (
            "observer-attachment-target-history-registry-head-identity::"
            "ObserverAttachmentTargetHistoryRegistryHead",
            "PRIOR_INSTALLED_ROOT",
        ),
        (
            "local-security-currentness-condition-projection-type::"
            "LocalSecurityCurrentnessConditionProjection",
            "LOCAL_SECURITY_CURRENTNESS_CONDITION_PROJECTION",
        ),
        (
            "authority-transaction-domain-qualification-receipt-type::"
            "AuthorityTransactionDomainQualificationReceipt",
            "AUTHORITY_TRANSACTION_DOMAIN_QUALIFICATION_RECEIPT",
        ),
        (
            "authority-transaction-domain-participant-set-type::"
            "AuthorityTransactionDomainParticipantSet",
            "AUTHORITY_TRANSACTION_DOMAIN_PARTICIPANT_SET",
        ),
        (
            "authority-transaction-domain-participant-role-policy-and-bounds-type::"
            "AuthorityTransactionDomainParticipantRolePolicyAndBounds",
            "AUTHORITY_TRANSACTION_STATIC_ROLE_POLICY_AND_BOUNDS",
        ),
    }
    consume_by_key = {
        (item["artifact"], item["role"]): item for item in event["consumes"]
    }
    require_exact(
        set(consume_by_key),
        required_consumes,
        "observer closure-aggregation exact consumes",
    )
    conditional_consume_cases = {
        (
            OBSERVER_GRANT_CLOSURE_AGGREGATION_EMPTY_UNIVERSE_PROOF,
            "EXACT_EMPTY_ACCEPTED_PLAN_PROOF",
        ): empty_universe_case_ids,
        (
            OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_EVIDENCE_BIJECTION,
            "EXACT_AFFECTED_MEMBER_NATIVE_EVIDENCE_BIJECTION",
        ): member_batch_case_ids,
        (
            (
                "observer-grant-distributed-authorization-closure-member-"
                "evidence-type::"
                "ObserverGrantDistributedAuthorizationClosureMemberEvidence"
            ),
            "PER_MEMBER_AUTHORIZATION_CLOSURE_NATIVE_EVIDENCE",
        ): member_batch_case_ids,
        (
            (
                "observer-grant-transport-quiescence-member-evidence-type::"
                "ObserverGrantTransportQuiescenceMemberEvidence"
            ),
            "PER_MEMBER_TRANSPORT_QUIESCENCE_NATIVE_EVIDENCE",
        ): member_batch_case_ids,
    }
    for consume_key, consume in consume_by_key.items():
        require_exact(
            set(consume.get("applies_to_semantic_case_ids", case_ids)),
            conditional_consume_cases.get(consume_key, set(case_ids)),
            f"observer closure-aggregation consume applicability {consume_key}",
        )
    expected_creates = {
        (
            "authority-transition-operation-commitment-type::"
            "AuthorityTransitionOperationCommitment",
            "AUTHORITY_TRANSITION_OPERATION_COMMITMENT",
        ),
        (
            "observer-attachment-target-history-registry-head-identity::"
            "ObserverAttachmentTargetHistoryRegistryHead",
            "CANDIDATE_SUCCESSOR_ROOT",
        ),
        (
            "observer-grant-closure-aggregation-candidate-type::"
            "ObserverGrantClosureAggregationCandidate",
            "CANDIDATE_SUCCESSOR_SUBSTATE",
        ),
    }
    actual_creates = {(item["artifact"], item["role"]) for item in event["creates"]}
    require_exact(
        actual_creates,
        expected_creates,
        "observer closure-aggregation created artifact/role set",
    )
    require_exact(
        {item["artifact"] for item in event["atomic_pre_cas_payloads"]},
        {
            "authority-transaction-cas-condition-type::AuthorityTransactionCASCondition",
            (
                "local-security-currentness-condition-projection-type::"
                "LocalSecurityCurrentnessConditionProjection"
            ),
            (
                "pre-cas-authority-semantic-commitment-type::"
                "PreCASAuthoritySemanticCommitment"
            ),
        },
        "observer closure-aggregation atomic payload set",
    )
    required_fact_bindings = {
        (
            "EXACT_EVENT_SEMANTIC_BINDING::OBSERVER_ATTACHMENT_TARGET_HISTORY."
            "ADVANCE_OBSERVER_GRANT_CLOSURE_AGGREGATION"
        ),
        "GRANTS_NO_AUTHORITY_AND_PRODUCES_NO_ALLOW_POLICY_RESULT",
        (
            "OBSERVER_ROLE_MARKER_IS_READ_COMPARE_PRESERVED_OR_TYPED_"
            "INAPPLICABLE_AND_NEVER_WRITTEN"
        ),
        (
            "AUTH_CLOSED_UNKNOWN_ONLY_FOR_DEADLINE_ELAPSED_OR_PERMANENT_"
            "AUTHORITY_ISOLATION_WITH_UNKNOWN_RETAINED_WORK"
        ),
        (
            "AUTH_CLOSED_EXACT_REQUIRES_EXACT_TERMINAL_NO_INSTALL_PENDING_"
            "NEVER_LIVE_OR_COMPLETE_ISOLATION_EVIDENCE"
        ),
        (
            "TRANSPORT_QUIESCENT_REQUIRES_SAME_MEMBER_EXACT_AUTHORIZATION_"
            "ANCESTRY_AND_ZERO_WORK_OR_COMPLETE_TRANSPORT_DISPOSITION"
        ),
        ("UNKNOWN_TO_TRANSPORT_QUIESCENT_AND_EVIDENCE_DOWNGRADE_ARE_FORBIDDEN"),
        (
            "AFFECTED_MEMBER_SET_IS_EXACT_DISJOINT_COMPLETE_AND_UNLISTED_"
            "MEMBERS_ARE_BYTE_PRESERVED"
        ),
        (
            "AUTHORIZATION_CLOSED_OUTPUT_IFF_EVERY_MEMBER_IS_AT_LEAST_"
            "AUTHORIZATION_CLOSED"
        ),
        "CALLER_SUPPLIED_OPERATION_ID_OR_NONCE_IS_FORBIDDEN",
        (
            "EXACT_EMPTY_INPUT_HAS_ZERO_MEMBER_WRITES_AND_ALL_PARTITIONS_EMPTY_"
            "WHILE_MEMBER_BATCH_HAS_ONE_OR_MORE_MEMBERS_EACH_IN_EXACTLY_ONE_"
            "PARTITION"
        ),
        (
            "EXACT_EVIDENCE_INPUT_CLOSED_UNION_EMPTY_OR_MEMBER_BATCH_WITH_NATIVE_"
            "ORIGIN_REQUIRED_AND_FORBIDDEN_FIELDS"
        ),
        (
            "EXACT_EVIDENCE_INPUT_COMMITMENT_ROOT_EMPTY_PROOF_OR_MEMBER_BIJECTION_"
            "BY_UNION_BRANCH"
        ),
        (
            "EXACT_FULL_GRANT_INSTALLATION_IDENTITY_ACCEPTED_RESULT_COMMITMENT_"
            "AND_IMMUTABLE_BOUNDARY_PLAN_MEMBER_ROOT_COUNT_BIJECTION"
        ),
        (
            "EXACT_PRE_CAS_SEMANTIC_INPUT_DIGEST_EXCLUDING_OPERATION_KEY_"
            "CANDIDATES_RECEIPTS_AND_SIDECARS"
        ),
        ("TRANSPORT_QUIESCENT_OUTPUT_IFF_EVERY_MEMBER_IS_TRANSPORT_QUIESCENT"),
        "EXACT_DERIVED_IDEMPOTENCY_OPERATION_AND_BYTE_IDENTICAL_REPLAY",
        ("TRANSPORT_QUIESCENT_RESULT_EXCLUDES_SIBLING_AUTHORIZATION_CLOSED_ENVELOPE"),
    }
    require(
        required_fact_bindings.issubset(
            set(event["pre_cas_content"]["required_bindings"])
        ),
        "observer closure-aggregation fact lacks fail-closed semantic bindings",
    )
    require_exact(
        {
            binding
            for binding in event["pre_cas_content"]["forbidden_bindings"]
            if binding.startswith("CALLER_SUPPLIED_")
        },
        {
            "CALLER_SUPPLIED_IDEMPOTENCY_KEY",
            "CALLER_SUPPLIED_OPERATION_ID",
        },
        "observer closure-aggregation caller-supplied identifier forbids",
    )
    require(
        "OPERATION_ID" not in event["pre_cas_content"]["required_bindings"],
        "observer closure aggregation requires a caller-selected operation ID",
    )
    mutated_resources = set(event["common_case_mutates"]) | {
        effect["resource"] for effect in event["common_case_effects"]
    }
    require(
        not any("OBSERVER_ROLE_MARKER" in resource for resource in mutated_resources),
        "observer closure aggregation writes an observer-role marker",
    )

    installed_root = (
        "authority-transaction-installed-state-root-type::"
        "AuthorityTransactionInstalledStateRoot"
    )
    transaction_receipt = (
        "authority-transaction-commit-receipt-type::AuthorityTransactionCommitReceipt"
    )
    generic_receipt = selector["generic_receipt"]
    aggregation_receipt = (
        "observer-grant-closure-aggregation-commit-receipt-type::"
        "ObserverGrantClosureAggregationCommitReceipt"
    )
    authorization_receipt = (
        "observer-grant-distributed-authorization-closure-receipt-type::"
        "ObserverGrantDistributedAuthorizationClosureReceipt"
    )
    transport_receipt = (
        "observer-grant-transport-quiescence-receipt-type::"
        "ObserverGrantTransportQuiescenceReceipt"
    )
    result_envelope = (
        "protected-observer-grant-closure-result-envelope-type::"
        "ProtectedObserverGrantClosureResultEnvelope"
    )
    pre_manifest = (
        "cross-store-producer-pre-manifest-bundle-commitment-type::"
        "CrossStoreProducerPreManifestBundleCommitment"
    )
    family_manifest = (
        "observer-grant-closure-result-publication-manifest-type::"
        "ObserverGrantClosureResultPublicationManifest"
    )
    completion_manifest = (
        "cross-store-producer-bundle-completion-manifest-type::"
        "CrossStoreProducerBundleCompletionManifest"
    )
    persistence_manifest = (
        "authority-transaction-persistence-manifest-type::"
        "AuthorityTransactionPersistenceManifest"
    )
    delivery_capsule = (
        "cross-store-protected-output-delivery-capsule-type::"
        "CrossStoreProtectedOutputDeliveryCapsule"
    )
    expected_sidecar_artifacts = {
        installed_root,
        transaction_receipt,
        generic_receipt,
        aggregation_receipt,
        authorization_receipt,
        transport_receipt,
        result_envelope,
        pre_manifest,
        family_manifest,
        completion_manifest,
        persistence_manifest,
        delivery_capsule,
    }
    sidecar_by_artifact = {
        sidecar["artifact"]: sidecar for sidecar in event["post_cas_sidecars"]
    }
    require_exact(
        set(sidecar_by_artifact),
        expected_sidecar_artifacts,
        "observer closure-aggregation sidecar set",
    )
    all_case_ids = set(case_ids)
    authorization_case_ids = (
        case_ids_by_variant["AUTHORIZATION_CLOSED"]
        | case_ids_by_variant["TRANSPORT_QUIESCENT_NONEMPTY"]
        | case_ids_by_variant["TRANSPORT_QUIESCENT_EMPTY_UNIVERSE"]
    )
    transport_case_ids = (
        case_ids_by_variant["TRANSPORT_QUIESCENT_NONEMPTY"]
        | case_ids_by_variant["TRANSPORT_QUIESCENT_EMPTY_UNIVERSE"]
    )
    no_result_case_ids = case_ids_by_variant["NO_COMPLETE_AGGREGATE"]

    def applicability(artifact: str) -> set[str]:
        return set(
            sidecar_by_artifact[artifact].get(
                "applies_to_semantic_case_ids",
                case_ids,
            )
        )

    for artifact in {
        installed_root,
        transaction_receipt,
        generic_receipt,
        aggregation_receipt,
        persistence_manifest,
    }:
        require_exact(
            applicability(artifact),
            all_case_ids,
            f"observer closure-aggregation {artifact} applicability",
        )
    require_exact(
        applicability(authorization_receipt),
        authorization_case_ids,
        "observer closure-aggregation authorization receipt applicability",
    )
    require_exact(
        applicability(transport_receipt),
        transport_case_ids,
        "observer closure-aggregation transport receipt applicability",
    )
    for artifact in {
        result_envelope,
        pre_manifest,
        family_manifest,
        completion_manifest,
        delivery_capsule,
    }:
        require_exact(
            applicability(artifact),
            authorization_case_ids,
            f"observer closure-aggregation {artifact} applicability",
        )
        require(
            applicability(artifact).isdisjoint(no_result_case_ids),
            (
                "observer closure aggregation emits a protected result "
                "hierarchy without a complete aggregate"
            ),
        )

    def effective_dependencies(artifact: str, case_id: str) -> set[str]:
        sidecar = sidecar_by_artifact[artifact]
        return set(sidecar["depends_on"]) | set(
            sidecar.get("depends_on_by_semantic_case", {}).get(case_id, [])
        )

    def dependency_ancestry(artifact: str, case_id: str) -> set[str]:
        ancestry: set[str] = set()
        pending = list(effective_dependencies(artifact, case_id))
        while pending:
            dependency = pending.pop()
            if dependency in ancestry:
                continue
            ancestry.add(dependency)
            if dependency in sidecar_by_artifact:
                pending.extend(effective_dependencies(dependency, case_id))
        return ancestry

    expected_static_dependencies = {
        installed_root: set(),
        transaction_receipt: {installed_root},
        generic_receipt: {transaction_receipt},
        aggregation_receipt: {generic_receipt, transaction_receipt},
        authorization_receipt: {aggregation_receipt},
        transport_receipt: {aggregation_receipt, authorization_receipt},
        result_envelope: {aggregation_receipt, authorization_receipt},
        pre_manifest: {result_envelope},
        family_manifest: {pre_manifest},
        completion_manifest: {family_manifest},
        persistence_manifest: {
            installed_root,
            transaction_receipt,
            generic_receipt,
            aggregation_receipt,
        },
        delivery_capsule: {
            result_envelope,
            family_manifest,
            completion_manifest,
            persistence_manifest,
        },
    }
    for artifact, expected_dependencies in expected_static_dependencies.items():
        require_exact(
            set(sidecar_by_artifact[artifact]["depends_on"]),
            expected_dependencies,
            f"observer closure-aggregation {artifact} exact static dependencies",
        )

    expected_result_dependencies_by_case = {
        case_id: ({transport_receipt} if case_id in transport_case_ids else set())
        for case_id in all_case_ids
    }
    expected_persistence_dependencies_by_case = {}
    for case_id in all_case_ids:
        dependencies: set[str] = set()
        if case_id in authorization_case_ids:
            dependencies.update(
                {
                    authorization_receipt,
                    result_envelope,
                    pre_manifest,
                    family_manifest,
                    completion_manifest,
                }
            )
        if case_id in transport_case_ids:
            dependencies.add(transport_receipt)
        expected_persistence_dependencies_by_case[case_id] = dependencies
    expected_case_dependencies = {
        result_envelope: expected_result_dependencies_by_case,
        persistence_manifest: expected_persistence_dependencies_by_case,
    }
    for artifact in expected_sidecar_artifacts:
        expected_by_case = expected_case_dependencies.get(artifact, {})
        actual_by_case = sidecar_by_artifact[artifact].get(
            "depends_on_by_semantic_case",
            {},
        )
        require_exact(
            set(actual_by_case),
            set(expected_by_case),
            f"observer closure-aggregation {artifact} dependency-case coverage",
        )
        for case_id, expected_dependencies in expected_by_case.items():
            require_exact(
                set(actual_by_case[case_id]),
                expected_dependencies,
                (
                    f"observer closure-aggregation {artifact} exact "
                    f"dependencies in {case_id}"
                ),
            )

    empty_universe_receipt_bindings = {
        case_id: [
            "EXACT_DOMAIN_SEPARATED_EMPTY_MEMBER_ROOT",
            "EXACT_EMPTY_UNIVERSE_DISCRIMINANT",
            "EXACT_EMPTY_UNIVERSE_PROOF_DIGEST",
        ]
        for case_id in empty_universe_case_ids
    }
    for artifact in expected_sidecar_artifacts:
        expected_bindings = (
            empty_universe_receipt_bindings
            if artifact
            in {
                aggregation_receipt,
                authorization_receipt,
                transport_receipt,
            }
            else {}
        )
        require_exact(
            sidecar_by_artifact[artifact].get(
                "additional_bindings_by_semantic_case",
                {},
            ),
            expected_bindings,
            f"observer closure-aggregation {artifact} case-specific bindings",
        )

    require_exact(
        sidecar_by_artifact[installed_root]["depends_on"],
        [],
        "observer closure-aggregation installed-root dependencies",
    )
    require_exact(
        sidecar_by_artifact[transaction_receipt]["depends_on"],
        [installed_root],
        "observer closure-aggregation transaction-receipt dependencies",
    )
    for case_id in all_case_ids:
        require(
            transaction_receipt in effective_dependencies(generic_receipt, case_id),
            "observer closure-aggregation generic receipt misses transaction",
        )
        require(
            {transaction_receipt, generic_receipt}.issubset(
                effective_dependencies(aggregation_receipt, case_id)
            ),
            "observer closure-aggregation commit receipt ancestry is incomplete",
        )
        for artifact in expected_sidecar_artifacts:
            if case_id not in applicability(artifact):
                continue
            dependencies = effective_dependencies(artifact, case_id)
            require(
                all(
                    case_id in applicability(dependency) for dependency in dependencies
                ),
                (
                    f"observer closure-aggregation {artifact} depends on a "
                    f"nonapplicable sidecar in {case_id}"
                ),
            )
    future_artifact_marker = "FUTURE_ARTIFACT::"
    for artifact in expected_sidecar_artifacts:
        expected_future_artifacts: set[str] = set()
        for case_id in applicability(artifact):
            require(
                artifact not in dependency_ancestry(artifact, case_id),
                (
                    "observer closure-aggregation sidecar dependency cycle "
                    f"through {artifact} in {case_id}"
                ),
            )
            expected_future_artifacts.update(
                descendant
                for descendant in expected_sidecar_artifacts
                if case_id in applicability(descendant)
                and artifact in dependency_ancestry(descendant, case_id)
            )
        actual_future_artifacts = {
            binding.removeprefix(future_artifact_marker)
            for binding in sidecar_by_artifact[artifact].get(
                "forbidden_bindings",
                [],
            )
            if binding.startswith(future_artifact_marker)
        }
        require_exact(
            actual_future_artifacts,
            expected_future_artifacts,
            f"observer closure-aggregation {artifact} exact future exclusions",
        )
    for case_id in authorization_case_ids:
        require(
            aggregation_receipt
            in effective_dependencies(authorization_receipt, case_id),
            "observer closure-aggregation authorization receipt lacks commit",
        )
        require(
            {
                aggregation_receipt,
                authorization_receipt,
                result_envelope,
            }.issubset(dependency_ancestry(pre_manifest, case_id)),
            "observer closure-aggregation pre-manifest ancestry is incomplete",
        )
        require(
            {result_envelope, pre_manifest}.issubset(
                dependency_ancestry(family_manifest, case_id)
            ),
            "observer closure-aggregation family manifest ancestry is incomplete",
        )
        require(
            {pre_manifest, family_manifest}.issubset(
                dependency_ancestry(completion_manifest, case_id)
            ),
            "observer closure-aggregation completion ancestry is incomplete",
        )
        require(
            completion_manifest
            in effective_dependencies(persistence_manifest, case_id),
            "observer closure-aggregation persistence omits completion manifest",
        )
        require(
            {
                persistence_manifest,
                completion_manifest,
                family_manifest,
                result_envelope,
            }.issubset(effective_dependencies(delivery_capsule, case_id)),
            "observer closure-aggregation delivery capsule ancestry is incomplete",
        )
    for case_id in case_ids_by_variant["AUTHORIZATION_CLOSED"]:
        require(
            authorization_receipt in effective_dependencies(result_envelope, case_id),
            "authorization-closed envelope lacks its aggregate receipt",
        )
    for case_id in transport_case_ids:
        require(
            {aggregation_receipt, authorization_receipt}.issubset(
                effective_dependencies(transport_receipt, case_id)
            ),
            "transport-quiescence receipt ancestry is incomplete",
        )
        require(
            {authorization_receipt, transport_receipt}.issubset(
                effective_dependencies(result_envelope, case_id)
            ),
            "transport-quiescent envelope lacks both aggregate receipts",
        )
    require(
        {
            "EXACT_DERIVED_RESULT_KIND_BY_SEMANTIC_CASE",
            "ONE_RESULT_ENVELOPE_MAXIMUM_PER_AGGREGATION_VERSION",
            ("TRANSPORT_QUIESCENT_EXCLUDES_SIBLING_AUTHORIZATION_CLOSED_ENVELOPE"),
        }.issubset(
            set(sidecar_by_artifact[result_envelope].get("additional_bindings", []))
        ),
        "observer closure-aggregation result envelope is not stronger-only",
    )


def _observer_grant_request_domain_contract_issues(
    selector: dict[str, Any],
) -> list[str]:
    """Keep the independent outer, local, and operation unions exact."""

    domain_by_id = {
        domain["state_domain"]: domain for domain in selector["state_domains"]
    }
    issues: list[str] = []
    for domain_id, expected in OBSERVER_GRANT_REQUEST_SPLIT_DOMAIN_CONTRACT.items():
        domain = domain_by_id.get(domain_id)
        if domain is None:
            issues.append(f"{domain_id}:MISSING_DOMAIN")
            continue
        for field in ("initial_state", "terminality"):
            if domain[field] != expected[field]:
                issues.append(
                    f"{domain_id}:{field.upper()}_MUST_EQUAL_"
                    f"{expected[field]}_ACTUAL_{domain[field]}"
                )
        for field in ("states", "terminal_states"):
            actual_values = set(domain[field])
            expected_values = expected[field]
            if actual_values != expected_values:
                issues.append(
                    f"{domain_id}:{field.upper()}_MUST_EQUAL_"
                    f"{sorted(expected_values)!r}_"
                    f"ACTUAL_{sorted(actual_values)!r}"
                )
        expected_root_safe = expected.get("root_terminal_safe_states")
        if expected_root_safe is not None:
            actual_root_safe = set(domain.get("root_terminal_safe_states", []))
            if actual_root_safe != expected_root_safe:
                issues.append(
                    f"{domain_id}:ROOT_TERMINAL_SAFE_STATES_MUST_EQUAL_"
                    f"{sorted(expected_root_safe)!r}_"
                    f"ACTUAL_{sorted(actual_root_safe)!r}"
                )
    if "ROOT" in domain_by_id:
        issues.append("ROOT:LEGACY_CONFLATED_OBSERVER_ADMISSION_DOMAIN_FORBIDDEN")
    return sorted(issues)


def _observer_grant_request_causal_liveness_diagnostic(
    data: dict[str, Any],
) -> dict[str, Any]:
    """Find closure paths that depend on an incompatible source outcome."""

    graph = _observer_grant_request_product_graph(data)
    selector = graph["selector"]
    event_by_id = {event["event_id"]: event for event in selector["events"]}
    resolver_cause_coverage = []
    for event_id in sorted(OBSERVER_GRANT_REQUEST_UNUSED_RESOLUTION_EVENTS):
        event = event_by_id.get(event_id)
        expected_causes = (
            {
                "SERVER_SLOT_CANCELED_UNUSED",
                "SERVER_SLOT_EXPIRED_UNUSED",
            }
            if event_id == OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT
            else set(OBSERVER_GRANT_REQUEST_TERMINAL_RESOLUTION_CAUSES)
        )
        derived_causes = (
            {
                cause
                for variant in event["decision_model"]["evidence_variant_definitions"]
                if (
                    cause := _observer_grant_request_case_resolution_cause(
                        event=event,
                        evidence_variant_id=variant["evidence_variant_id"],
                    )
                )
                is not None
            }
            if event is not None
            else set()
        )
        unclassified_variant_ids = (
            sorted(
                variant["evidence_variant_id"]
                for variant in event["decision_model"]["evidence_variant_definitions"]
                if (
                    _observer_grant_request_case_resolution_cause(
                        event=event,
                        evidence_variant_id=variant["evidence_variant_id"],
                    )
                    is None
                )
            )
            if event is not None
            else []
        )
        resolver_cause_coverage.append(
            {
                "event_id": event_id,
                "missing_exact_cause_variant_ids": sorted(
                    expected_causes - derived_causes
                ),
                "unclassified_variant_ids": (unclassified_variant_ids),
            }
        )

    missing_rows: list[str] = []
    for kind in sorted(OBSERVER_GRANT_REQUEST_KINDS):
        initial_state = graph["start_product"][kind]
        for initial_scenario in [OBSERVER_GRANT_REQUEST_INITIAL_CAUSAL_STATE]:
            missing = _product_states_without_terminal_path(
                initial_state=(*initial_state, initial_scenario),
                transitions=graph["causal_transitions_by_kind"][kind],
                terminal_states=graph["causal_terminal_products"],
            )
            for causal_product_state in sorted(missing):
                product_state = causal_product_state[:-1]
                current_scenario = causal_product_state[-1]
                disposition = (
                    "UNUSED_TERMINAL"
                    if current_scenario
                    in {
                        "SERVER_SLOT_CANCELED_UNUSED",
                        "SERVER_SLOT_EXPIRED_UNUSED",
                    }
                    else current_scenario
                )
                missing_rows.append(
                    ".".join(
                        [
                            kind,
                            f"INITIAL_CAUSAL_STATE={initial_scenario}",
                            f"CAUSAL_DISPOSITION={disposition}",
                            f"CURRENT_CAUSAL_STATE={current_scenario}",
                            *(
                                f"{domain_id}={state}"
                                for domain_id, state in zip(
                                    graph["product_domain_ids"],
                                    product_state,
                                    strict=True,
                                )
                            ),
                        ]
                    )
                )
    return {
        "causal_dispositions": sorted(OBSERVER_GRANT_REQUEST_CAUSAL_DISPOSITIONS),
        "claim_boundary": (
            "KIND_AND_MONOTONE_VERIFIED_SOURCE_OUTCOME_REFINED_SINGLE_"
            "REQUEST_KEY_"
            "NECESSARY_CONDITION_LINT_A_PASS_DOES_NOT_PROVE_EVIDENCE_"
            "AUTHENTICITY_MULTI_KEY_REACHABILITY_SCHEDULING_FAIRNESS_"
            "DURATION_NETWORK_OR_EXTERNAL_QUALIFICATION"
        ),
        "domain_mode": graph["domain_mode"],
        "domain_contract_issues": (
            _observer_grant_request_domain_contract_issues(selector)
        ),
        "evidence_contract_issues": (
            _observer_grant_request_evidence_contract_issues(selector)
        ),
        "cross_store_publication_manifest_contract_issues": (
            _cross_store_publication_manifest_contract_issues(data)
        ),
        "missing_operation_event_ids": graph["missing_operation_event_ids"],
        "resolver_cause_coverage": resolver_cause_coverage,
        "states_without_terminal_path": missing_rows,
        "successor_contract_issues": (
            _observer_grant_request_successor_contract_issues(selector)
        ),
        "terminal_resolution_cause_to_disposition": {
            cause: OBSERVER_GRANT_REQUEST_CAUSE_DISPOSITION[cause]
            for cause in sorted(OBSERVER_GRANT_REQUEST_TERMINAL_RESOLUTION_CAUSES)
        },
        "transition_contract_issues": (
            _observer_grant_request_causal_transition_contract_issues(selector)
        ),
        "unclassified_sensitive_variants": graph["unclassified_sensitive_variants"],
        "unclassified_kind_variants": graph["unclassified_kind_variants"],
    }


def _validate_observer_grant_request_product_liveness(
    data: dict[str, Any],
    *,
    allow_known_incomplete: bool,
) -> None:
    """Reject request-kind control products that can strand an operation."""

    if allow_known_incomplete:
        return
    missing = _observer_grant_request_product_liveness_rows(data)
    require(
        not missing,
        (
            "OBSERVER_ADMISSION: request-kind control-product states lack "
            f"a modeled terminal path: count={len(missing)} "
            f"sample={missing[:3]}"
        ),
    )
    causal = _observer_grant_request_causal_liveness_diagnostic(data)
    require_exact(
        causal["domain_mode"],
        "SPLIT_OUTER_LIFECYCLE_AND_LOCAL_GRANT_STATE",
        "OBSERVER_ADMISSION request-product domain separation",
    )
    require(
        not causal["domain_contract_issues"],
        (
            "OBSERVER_ADMISSION: request-product state-domain unions, "
            "initial states, terminal states, or separation differ from "
            f"the closed contract: {causal['domain_contract_issues']}"
        ),
    )
    require(
        not causal["missing_operation_event_ids"],
        (
            "OBSERVER_ADMISSION: request-product operation event set is "
            f"incomplete: {causal['missing_operation_event_ids']}"
        ),
    )
    incomplete_resolver_coverage = [
        row
        for row in causal["resolver_cause_coverage"]
        if row["missing_exact_cause_variant_ids"] or row["unclassified_variant_ids"]
    ]
    require(
        not incomplete_resolver_coverage,
        (
            "OBSERVER_ADMISSION: without-installation resolver variants "
            "must equal the closed terminal-resolution cause union: "
            f"{incomplete_resolver_coverage}"
        ),
    )
    require(
        not causal["unclassified_sensitive_variants"],
        (
            "OBSERVER_ADMISSION: request resolver cases have ambiguous "
            "or unclassified source outcomes: "
            f"{causal['unclassified_sensitive_variants']}"
        ),
    )
    require(
        not causal["unclassified_kind_variants"],
        (
            "OBSERVER_ADMISSION: shared request-operation cases must derive "
            "one exact ATTACH/REATTACH/RENEW kind: "
            f"{causal['unclassified_kind_variants']}"
        ),
    )
    require(
        not causal["transition_contract_issues"],
        (
            "OBSERVER_ADMISSION: cause-sensitive request operation "
            "transitions violate install/observe/resolve polarity or exact "
            f"retry closure: {causal['transition_contract_issues']}"
        ),
    )
    require(
        not causal["successor_contract_issues"],
        (
            "OBSERVER_ADMISSION: kind/cause local successor or deny-phase "
            "coverage is incomplete or permissive: "
            f"{causal['successor_contract_issues']}"
        ),
    )
    require(
        not causal["evidence_contract_issues"],
        (
            "OBSERVER_ADMISSION: request-cause evidence is incomplete, "
            "self-asserted, or not disjoint: "
            f"{causal['evidence_contract_issues']}"
        ),
    )
    require(
        not causal["cross_store_publication_manifest_contract_issues"],
        (
            "observer activation or boundary closure consumes an envelope "
            "without exact complete-publication membership: "
            f"{causal['cross_store_publication_manifest_contract_issues']}"
        ),
    )
    require(
        not causal["states_without_terminal_path"],
        (
            "OBSERVER_ADMISSION: cause-refined request-product states lack "
            "a same-kind, evidence-compatible terminal path: "
            f"count={len(causal['states_without_terminal_path'])} "
            f"sample={causal['states_without_terminal_path'][:3]}"
        ),
    )


def _candidate_allocation_adr_id(
    allocation: ModelAllocation,
    *,
    accepted_prose_identifiers: dict[str, set[str]],
) -> str:
    """Suggest one defining ADR for review; this is not oracle authority."""

    kind = allocation.kind
    exact_name = allocation.exact_name
    semantic_ref = allocation.semantic_ref

    declaration_selector_ids: set[str] = set()
    if kind == "SELECTOR":
        declaration_selector_ids.add(exact_name)
    elif kind == "RESOURCE":
        declaration_selector_ids.add(exact_name.split(".", 1)[0])
    elif kind == "STATE":
        state_match = STATE_SEMANTIC_REF.fullmatch(semantic_ref)
        require(
            state_match is not None,
            f"inventory-gap report has an invalid STATE ref {semantic_ref}",
        )
        declaration_selector_ids.add(state_match.group(1))
    elif kind == "EVENT":
        for origin in allocation.origins:
            match = re.match(
                r"^selector-id::([A-Z][A-Z0-9_]*)/event-id::",
                origin.semantic_location,
            )
            if match is not None:
                declaration_selector_ids.add(match.group(1))

    def body_type_is_adr006() -> bool:
        return exact_name.startswith(CANDIDATE_BODY_ADR006_TYPE_PREFIXES) or (
            exact_name.startswith("BodySessionControl")
            and any(
                fragment in exact_name
                for fragment in CANDIDATE_BODY_CONTROL_ADR006_TYPE_FRAGMENTS
            )
        )

    if kind == "PROFILE":
        if semantic_ref.startswith("/actor_profiles/"):
            return "ADR-011"
        if semantic_ref.startswith("/closed_event_profile_catalog/"):
            return "ADR-001"
        if semantic_ref.startswith("/joint_selector_transaction_profiles/"):
            return (
                "ADR-001"
                if exact_name in CANDIDATE_ADR001_JOINT_PROFILES
                else "ADR-004"
            )
        if semantic_ref.startswith("/sidecar_binding_profiles/"):
            return "ADR-001"
        root_profile_key = (
            semantic_ref.split("/", 2)[1] if semantic_ref.startswith("/") else ""
        )
        if root_profile_key in CANDIDATE_PROFILE_ADR_SUGGESTION:
            return CANDIDATE_PROFILE_ADR_SUGGESTION[root_profile_key]
        return CANDIDATE_PROFILE_ADR_SUGGESTION.get(
            exact_name,
            "UNMAPPED_SHARED",
        )

    if declaration_selector_ids == {"BODY_SESSION_CONTROL"}:
        if kind == "STATE":
            state_match = STATE_SEMANTIC_REF.fullmatch(semantic_ref)
            require(state_match is not None, "invalid body STATE semantic reference")
            state_domain = state_match.group(2)
            return (
                "ADR-006"
                if state_domain in CANDIDATE_BODY_ADR006_STATE_DOMAINS
                else "ADR-007"
            )
        if kind == "RESOURCE" and exact_name.startswith(
            "BODY_SESSION_CONTROL.STATE_DOMAIN."
        ):
            state_domain = exact_name.rsplit(".", 1)[1]
            return (
                "ADR-006"
                if state_domain in CANDIDATE_BODY_ADR006_STATE_DOMAINS
                else "ADR-007"
            )
        if kind == "EVENT":
            return (
                "ADR-006"
                if exact_name in accepted_prose_identifiers["ADR-006"]
                else "ADR-007"
            )
        if body_type_is_adr006():
            return "ADR-006"
        return "ADR-007"
    if len(declaration_selector_ids) == 1:
        selector_id = next(iter(declaration_selector_ids))
        return CANDIDATE_SELECTOR_ADR_SUGGESTION.get(
            selector_id,
            "UNMAPPED_SHARED",
        )

    if exact_name.startswith(
        (
            "ProtectedSourceLogicalSessionCooperativeAnchor",
            "ProtectedSourceLogicalSessionNamespaceAnchor",
            "SourceLogicalSessionCooperativeAnchor",
            "SourceLogicalSessionNamespaceAnchor",
        )
    ):
        return "ADR-004"
    slug = semantic_ref.split("::", 1)[0]
    if slug.startswith("cross-store-"):
        return "ADR-009"
    if slug.startswith("forwarding-"):
        return "ADR-003"
    if slug.startswith(
        (
            "imported-realm-security-",
            "installed-security-",
            "local-security-",
            "security-authority-",
        )
    ):
        return "ADR-009"
    if slug.startswith(
        (
            "anchor-observer-",
            "independent-anchor-",
            "installed-independent-anchor-",
            "observer-",
            "protected-independent-anchor-",
            "protected-observer-",
            "protected-trusted-delivery-",
            "qualified-observer-",
            "qualified-permanent-source-isolation-",
            "trusted-delivery-",
        )
    ):
        return "ADR-004"
    if slug.startswith(
        (
            "declaration-",
            "frame-admission-",
            "historical-admission-",
            "receiver-evidence-",
        )
    ):
        return "ADR-005"
    if slug.startswith(("authorization-deadline-", "retention-quiescence-")):
        return "ADR-004"
    if slug.startswith("typed-deadline-"):
        return "ADR-006"
    if slug.startswith(("actuation-authority-", "physical-actuation-")):
        return "ADR-007"
    if slug.startswith("body-"):
        if body_type_is_adr006():
            return "ADR-006"
        return "ADR-007"
    return "UNMAPPED_SHARED"


def _minimum_extractable_identifier_bytes(
    exact_names: set[str] | list[str],
) -> int:
    """Count separately delimited single-backtick identifiers and separators."""

    return sum(len(exact_name.encode("utf-8")) + 2 for exact_name in exact_names) + max(
        0, len(exact_names) - 1
    )


def _candidate_capacity_projection(
    data: dict[str, Any],
    *,
    accepted_prose_identifiers: dict[str, set[str]],
    current_document_rows: list[dict[str, Any]],
    registerable_missing_artifact_refs: list[str],
) -> dict[str, Any]:
    """Measure external-inventory storage after non-alias registry additions."""

    from generate_selector_closure_source import (
        _recompute_closure_commitments,
    )

    projection = copy.deepcopy(data)
    projection["artifacts"] = sorted(
        set(projection["artifacts"]) | set(registerable_missing_artifact_refs)
    )
    model = _model_allocations(projection)
    routed_model = [
        (
            allocation,
            _candidate_allocation_adr_id(
                allocation,
                accepted_prose_identifiers=accepted_prose_identifiers,
            ),
        )
        for allocation in model
    ]
    unmapped_shared_units = [
        allocation
        for allocation, candidate_adr_id in routed_model
        if candidate_adr_id == "UNMAPPED_SHARED"
    ]
    allocation_rows = [
        {
            "adr_id": candidate_adr_id,
            "exact_name": allocation.exact_name,
            "kind": allocation.kind,
            "semantic_ref": allocation.semantic_ref,
            "source_anchor": ADR_ALLOCATION_ANCHOR_BY_ID[candidate_adr_id],
            "unit_id": allocation.unit_id,
        }
        for allocation, candidate_adr_id in routed_model
        if candidate_adr_id != "UNMAPPED_SHARED"
    ]
    allocation_rows.sort(
        key=lambda row: (
            row["adr_id"],
            row["kind"],
            row["exact_name"],
            row["semantic_ref"],
            row["unit_id"],
        )
    )
    allocation_pairs = {(row["adr_id"], row["exact_name"]) for row in allocation_rows}
    exclusion_rows = copy.deepcopy(projection["adr_allocation_oracle"]["exclusions"])
    exclusion_pairs = {(row["adr_id"], row["exact_name"]) for row in exclusion_rows}
    final_pairs = allocation_pairs | exclusion_pairs
    document_by_adr = {row["adr_id"]: row for row in current_document_rows}
    documents = projection["adr_allocation_oracle"]["documents"]
    for document in documents:
        adr_id = document["adr_id"]
        per_adr_allocations = [
            row for row in allocation_rows if row["adr_id"] == adr_id
        ]
        per_adr_exclusions = [row for row in exclusion_rows if row["adr_id"] == adr_id]
        document.clear()
        document.update(copy.deepcopy(document_by_adr[adr_id]))
        document["allocation_anchor_id"] = ADR_ALLOCATION_ANCHOR_BY_ID[adr_id]
        document["allocation_row_count"] = len(per_adr_allocations)
        document["allocation_rows_sha256"] = document_rows_sha256(
            per_adr_allocations,
            row_kind="allocations",
        )
        document["exclusion_row_count"] = len(per_adr_exclusions)
        document["exclusion_rows_sha256"] = document_rows_sha256(
            per_adr_exclusions,
            row_kind="exclusions",
        )

    oracle = projection["adr_allocation_oracle"]
    oracle["allocations"] = allocation_rows
    oracle["document_row_commitment"] = copy.deepcopy(DOCUMENT_ROW_COMMITMENT)
    oracle["exclusions"] = exclusion_rows
    oracle["model_allocation_count"] = len(model)
    oracle["model_allocation_sha256"] = _model_allocation_sha256(model)
    oracle["provenance_review"] = build_not_reviewed_provenance_review()
    oracle["status"] = "INCOMPLETE_FAIL_CLOSED"
    shape_count, shape_digest = _semantic_shape_commitment(projection)
    oracle["semantic_shape_entry_count"] = shape_count
    oracle["semantic_shape_sha256"] = shape_digest
    review_profile = oracle["allocation_review_profile"]
    review_profile["model_allocation_count"] = len(model)
    review_profile["model_allocation_sha256"] = _model_allocation_sha256(model)
    (
        review_profile["model_origin_signal_row_count"],
        review_profile["model_origin_signal_sha256"],
    ) = _model_origin_signal_commitment(model)
    review_profile["model_origin_signal_projection_schema"] = (
        MODEL_ORIGIN_SIGNAL_PROJECTION_SCHEMA
    )
    review_profile["required_kinds"] = list(ALLOCATION_KINDS)
    review_profile["semantic_shape_entry_count"] = shape_count
    review_profile["semantic_shape_sha256"] = shape_digest
    oracle["semantic_review_subject"] = semantic_review_subject_commitment(projection)
    _recompute_closure_commitments(projection)

    expanded_bytes = len(canonical_bytes(projection)) + 1
    envelope = compact_selector_source(projection)
    compact_bytes = len(canonical_bytes(envelope)) + 1
    string_table_count = len(envelope["encoding"]["string_table"])
    object_table_count = len(envelope["encoding"]["object_table"])
    return {
        "allocation_row_count": len(allocation_rows),
        "allocation_identifier_pair_count": len(allocation_pairs),
        "claim_boundary": (
            "STORAGE_CAPACITY_PROJECTION_ONLY_NOT_SEMANTIC_VALIDATION_"
            "ALLOCATION_AUTHORITY_OR_FREEZE"
        ),
        "compact_byte_margin": MAX_COMPACT_BYTES - compact_bytes,
        "compact_bytes": compact_bytes,
        "expanded_byte_margin": MAX_EXPANDED_BYTES - expanded_bytes,
        "expanded_bytes": expanded_bytes,
        "external_identifier_pair_count": len(final_pairs),
        "former_2_mib_compact_overage": (compact_bytes - (2 * 1024 * 1024)),
        "object_table_entry_count": object_table_count,
        "object_table_entry_margin": (MAX_TABLE_ITEMS - object_table_count),
        "string_table_entry_count": string_table_count,
        "string_table_entry_margin": (MAX_TABLE_ITEMS - string_table_count),
        "typed_exclusion_row_count": len(exclusion_rows),
        "unmapped_shared_unit_count": len(unmapped_shared_units),
        "unmapped_shared_unit_ids": sorted(
            allocation.unit_id for allocation in unmapped_shared_units
        ),
    }


def _decision_relation_coverage_diagnostic(
    data: dict[str, Any],
) -> dict[str, Any]:
    """Measure explicit variant fields without treating density as correctness."""

    selector_rows: list[dict[str, Any]] = []
    totals = {
        "event_count": 0,
        "events_with_only_fieldless_variants": 0,
        "events_with_only_receipt_variants": 0,
        "evidence_variant_count": 0,
        "evidence_variants_without_specific_required_fields": 0,
        "receipt_only_evidence_variants": 0,
    }
    for selector in data["selectors"]:
        selector_counts = {
            "event_count": len(selector["events"]),
            "events_with_only_fieldless_variants": 0,
            "events_with_only_receipt_variants": 0,
            "evidence_variant_count": 0,
            "evidence_variants_without_specific_required_fields": 0,
            "receipt_only_evidence_variants": 0,
        }
        for event in selector["events"]:
            variants = event["decision_model"]["evidence_variant_definitions"]
            fieldless = [
                variant for variant in variants if not variant["required_fields"]
            ]
            receipt_only = [
                variant
                for variant in variants
                if not variant["required_fields"]
                and len(variant["truth_conditions"]) == 1
                and variant["truth_conditions"][0]["field"]
                == "PRE_CAS_CONTENT.typed_fact_validation_receipt"
            ]
            selector_counts["evidence_variant_count"] += len(variants)
            selector_counts["evidence_variants_without_specific_required_fields"] += (
                len(fieldless)
            )
            selector_counts["receipt_only_evidence_variants"] += len(receipt_only)
            selector_counts["events_with_only_fieldless_variants"] += len(
                fieldless
            ) == len(variants)
            selector_counts["events_with_only_receipt_variants"] += len(
                receipt_only
            ) == len(variants)
        selector_rows.append(
            {
                **selector_counts,
                "selector_id": selector["selector_id"],
            }
        )
        for key, value in selector_counts.items():
            totals[key] += value
    return {
        "claim_boundary": (
            "STRUCTURAL_DECISION_RELATION_DENSITY_DIAGNOSTIC_ONLY_"
            "NONEMPTY_FIELDS_DO_NOT_PROVE_CORRECTNESS_AND_EMPTY_FIELDS_DO_"
            "NOT_BY_THEMSELVES_PROVE_UNSAFETY"
        ),
        **totals,
        "selectors": selector_rows,
    }


def _run_decision_relation_coverage_self_test() -> int:
    receipt_condition = {"field": "PRE_CAS_CONTENT.typed_fact_validation_receipt"}
    other_condition = {"field": "PRE_CAS_CONTENT.exact_remote_proof"}
    data = {
        "selectors": [
            {
                "events": [
                    {
                        "decision_model": {
                            "evidence_variant_definitions": [
                                {
                                    "required_fields": [],
                                    "truth_conditions": [receipt_condition],
                                },
                                {
                                    "required_fields": [
                                        "PRE_CAS_CONTENT.exact_remote_proof"
                                    ],
                                    "truth_conditions": [other_condition],
                                },
                            ]
                        }
                    },
                    {
                        "decision_model": {
                            "evidence_variant_definitions": [
                                {
                                    "required_fields": [],
                                    "truth_conditions": [other_condition],
                                }
                            ]
                        }
                    },
                ],
                "selector_id": "SYNTHETIC",
            }
        ]
    }
    report = _decision_relation_coverage_diagnostic(data)
    require_exact(
        {
            key: report[key]
            for key in (
                "event_count",
                "events_with_only_fieldless_variants",
                "events_with_only_receipt_variants",
                "evidence_variant_count",
                "evidence_variants_without_specific_required_fields",
                "receipt_only_evidence_variants",
            )
        },
        {
            "event_count": 2,
            "events_with_only_fieldless_variants": 1,
            "events_with_only_receipt_variants": 0,
            "evidence_variant_count": 3,
            "evidence_variants_without_specific_required_fields": 2,
            "receipt_only_evidence_variants": 1,
        },
        "decision-relation density totals",
    )
    require_exact(
        report["selectors"][0]["selector_id"],
        "SYNTHETIC",
        "decision-relation density selector grouping",
    )
    return 2


def _candidate_semantic_review_summary(
    candidate_gap_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Group non-provenanced candidate pairs without weakening row detail."""

    review_rows = [
        row
        for row in candidate_gap_rows
        if row["classification"] == "ADR_SEMANTIC_REVIEW_REQUIRED"
    ]
    kind_counts: dict[str, int] = {}
    origin_kind_counts: dict[str, int] = {}
    provenance_signal_counts: dict[str, int] = {}
    per_adr_counts: dict[str, dict[str, int | dict[str, int]]] = {}
    for row in review_rows:
        kinds = sorted({model_row["kind"] for model_row in row["model_rows"]})
        origin_kinds = sorted(
            {
                origin["evidence_kind"]
                for model_row in row["model_rows"]
                for origin in model_row["origins"]
            }
        )
        kind_category = "+".join(kinds)
        origin_category = "+".join(origin_kinds)
        kind_counts[kind_category] = kind_counts.get(kind_category, 0) + 1
        origin_kind_counts[origin_category] = (
            origin_kind_counts.get(origin_category, 0) + 1
        )
        provenance_signal = row["provenance_signal"]
        provenance_signal_counts[provenance_signal] = (
            provenance_signal_counts.get(provenance_signal, 0) + 1
        )
        adr_counts = per_adr_counts.setdefault(
            row["adr_id"],
            {
                "identifier_pair_count": 0,
                "model_kind_counts": {},
                "model_origin_kind_counts": {},
                "provenance_signal_counts": {},
            },
        )
        adr_counts["identifier_pair_count"] += 1
        adr_kind_counts = adr_counts["model_kind_counts"]
        require(
            isinstance(adr_kind_counts, dict),
            "semantic-review summary kind-count accumulator is invalid",
        )
        adr_kind_counts[kind_category] = adr_kind_counts.get(kind_category, 0) + 1
        adr_origin_counts = adr_counts["model_origin_kind_counts"]
        require(
            isinstance(adr_origin_counts, dict),
            "semantic-review summary origin-count accumulator is invalid",
        )
        adr_origin_counts[origin_category] = (
            adr_origin_counts.get(origin_category, 0) + 1
        )
        adr_signal_counts = adr_counts["provenance_signal_counts"]
        require(
            isinstance(adr_signal_counts, dict),
            "semantic-review summary signal-count accumulator is invalid",
        )
        adr_signal_counts[provenance_signal] = (
            adr_signal_counts.get(provenance_signal, 0) + 1
        )

    def sorted_counts(counts: dict[str, int]) -> dict[str, int]:
        return {key: counts[key] for key in sorted(counts)}

    by_adr = {}
    for adr_id in sorted(per_adr_counts):
        counts = per_adr_counts[adr_id]
        adr_kind_counts = counts["model_kind_counts"]
        adr_origin_counts = counts["model_origin_kind_counts"]
        adr_signal_counts = counts["provenance_signal_counts"]
        require(
            isinstance(adr_kind_counts, dict)
            and isinstance(adr_origin_counts, dict)
            and isinstance(adr_signal_counts, dict),
            "semantic-review summary per-ADR accumulator is invalid",
        )
        by_adr[adr_id] = {
            "identifier_pair_count": counts["identifier_pair_count"],
            "model_kind_counts": sorted_counts(adr_kind_counts),
            "model_origin_kind_counts": sorted_counts(adr_origin_counts),
            "provenance_signal_counts": sorted_counts(adr_signal_counts),
        }
    return {
        "by_candidate_assignment_adr": by_adr,
        "claim_boundary": (
            "MECHANICAL_PROVENANCE_SIGNAL_ONLY_NOT_NORMATIVE_OR_STALE_CLASSIFICATION"
        ),
        "identifier_pair_count": len(review_rows),
        "model_kind_counts": sorted_counts(kind_counts),
        "model_origin_kind_counts": sorted_counts(origin_kind_counts),
        "provenance_signal_counts": sorted_counts(provenance_signal_counts),
    }


def _run_candidate_semantic_review_summary_self_test() -> int:
    require_exact(
        _minimum_extractable_identifier_bytes(["A", "β"]),
        8,
        "individually delimited UTF-8 identifier capacity",
    )
    rows = [
        {
            "adr_id": "ADR-001",
            "classification": "ADR_SEMANTIC_REVIEW_REQUIRED",
            "model_rows": [
                {
                    "kind": "TYPE",
                    "origins": [
                        {"evidence_kind": "ARTIFACT_REGISTRY_ENTRY"},
                    ],
                },
                {
                    "kind": "TYPE",
                    "origins": [
                        {"evidence_kind": "RESOURCE_DECLARATION"},
                    ],
                },
            ],
            "provenance_signal": ("EXACT_NAME_IN_ACCEPTED_SECTION_OF_OTHER_ADR"),
        },
        {
            "adr_id": "ADR-001",
            "classification": "ADR_SEMANTIC_REVIEW_REQUIRED",
            "model_rows": [
                {
                    "kind": "STATE",
                    "origins": [
                        {"evidence_kind": "STATE_DECLARATION"},
                    ],
                },
            ],
            "provenance_signal": "NO_ADR_PROSE_OR_INVENTORY_OCCURRENCE",
        },
        {
            "adr_id": "ADR-002",
            "classification": "EXTERNAL_INVENTORY_ONLY",
            "model_rows": [
                {
                    "kind": "EVENT",
                    "origins": [
                        {"evidence_kind": "DECLARED_EVENT"},
                    ],
                },
            ],
            "provenance_signal": "IGNORED",
        },
    ]
    summary = _candidate_semantic_review_summary(rows)
    require_exact(
        summary["identifier_pair_count"],
        2,
        "semantic-review summary filter",
    )
    require_exact(
        summary["by_candidate_assignment_adr"]["ADR-001"],
        {
            "identifier_pair_count": 2,
            "model_kind_counts": {"STATE": 1, "TYPE": 1},
            "model_origin_kind_counts": {
                "ARTIFACT_REGISTRY_ENTRY+RESOURCE_DECLARATION": 1,
                "STATE_DECLARATION": 1,
            },
            "provenance_signal_counts": {
                "EXACT_NAME_IN_ACCEPTED_SECTION_OF_OTHER_ADR": 1,
                "NO_ADR_PROSE_OR_INVENTORY_OCCURRENCE": 1,
            },
        },
        "semantic-review summary grouping",
    )
    return 3


def build_inventory_gap_report(data: dict[str, Any]) -> dict[str, Any]:
    """Build a read-only moving-corpus diagnostic; never allocate or freeze."""

    snapshots: dict[Path, bytes] = {}
    document_rows: list[dict[str, Any]] = []
    oracle = data["adr_allocation_oracle"]
    inventory_allocations = oracle["allocations"]
    inventory_exclusions = oracle["exclusions"]
    external_identifiers: dict[str, set[str]] = {
        f"ADR-{index:03d}": set() for index in range(1, len(ADR_ALLOCATION_PATHS) + 1)
    }
    for row in [*inventory_allocations, *inventory_exclusions]:
        adr_id = row["adr_id"]
        require(
            adr_id in external_identifiers,
            f"inventory-gap external row has unknown ADR ID {adr_id!r}",
        )
        require_exact(
            row["source_anchor"],
            ADR_ALLOCATION_ANCHOR_BY_ID[adr_id],
            "inventory-gap external row anchor",
        )
        external_identifiers[adr_id].add(row["exact_name"])
    accepted_prose_identifiers: dict[str, set[str]] = {}
    prose_identifier_tokens: dict[str, set[str]] = {}
    corpus_bytes = 0
    source_file_identities: dict[tuple[int, int], Path] = {}
    for index, relative_path in enumerate(ADR_ALLOCATION_PATHS, 1):
        path = Path(relative_path)
        adr_id = f"ADR-{index:03d}"
        raw = read_bounded_regular_file(
            ROOT / path,
            maximum_bytes=MAX_ADR_BYTES,
            label=f"{adr_id} inventory-gap source",
        )
        snapshots[path] = raw
        corpus_bytes += len(raw)
        source_stat = os.stat(ROOT / path, follow_symlinks=False)
        source_identity = (source_stat.st_dev, source_stat.st_ino)
        require(
            source_identity not in source_file_identities,
            f"{adr_id}: inventory-gap main source aliases another ADR source",
        )
        source_file_identities[source_identity] = path
        require(
            corpus_bytes <= MAX_ADR_CORPUS_BYTES,
            (f"inventory-gap ADR corpus exceeds {MAX_ADR_CORPUS_BYTES} bytes"),
        )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            fail(f"{adr_id}: invalid UTF-8: {error}")
        anchor_id = _extract_allocation_anchor(
            text,
            expected_anchor_id=ADR_ALLOCATION_ANCHOR_BY_ID[adr_id],
            label=adr_id,
        )
        source_texts = [text]
        module_rows: list[dict[str, Any]] = []
        for module_index, module_path_text in enumerate(
            ADR_ALLOCATION_MODULE_PATHS[index - 1]
        ):
            module_path = Path(module_path_text)
            module_raw = read_bounded_regular_file(
                ROOT / module_path,
                maximum_bytes=MAX_ADR_BYTES,
                label=f"{adr_id} inventory-gap module {module_index}",
            )
            snapshots[module_path] = module_raw
            corpus_bytes += len(module_raw)
            require(
                corpus_bytes <= MAX_ADR_CORPUS_BYTES,
                (f"inventory-gap ADR corpus exceeds {MAX_ADR_CORPUS_BYTES} bytes"),
            )
            module_stat = os.stat(ROOT / module_path, follow_symlinks=False)
            module_identity = (module_stat.st_dev, module_stat.st_ino)
            require(
                module_identity not in source_file_identities,
                f"{adr_id}: inventory-gap module aliases another ADR source",
            )
            source_file_identities[module_identity] = module_path
            try:
                module_text = module_raw.decode("utf-8")
            except UnicodeDecodeError as error:
                fail(f"{adr_id} module {module_index}: invalid UTF-8: {error}")
            require(
                not ALLOCATION_ANCHOR_RE.findall(module_text),
                (
                    f"{adr_id} module {module_index}: stable allocation "
                    "anchor must remain in the main ADR"
                ),
            )
            source_texts.append(module_text)
            module_rows.append(
                {
                    "byte_length": len(module_raw),
                    "path": module_path_text,
                    "sha256": sha256(module_raw).hexdigest(),
                }
            )
        accepted_prose_identifiers[adr_id] = set().union(
            *(
                _accepted_allocation_prose_identifiers(source_text)
                for source_text in source_texts
            )
        )
        prose_identifier_tokens[adr_id] = set().union(
            *(
                set(IDENTIFIER_TOKEN_RE.findall(source_text))
                for source_text in source_texts
            )
        )
        allocation_rows = [
            row for row in inventory_allocations if row["adr_id"] == adr_id
        ]
        exclusion_rows = [
            row for row in inventory_exclusions if row["adr_id"] == adr_id
        ]
        document_row = {
            "adr_id": adr_id,
            "allocation_anchor_id": anchor_id,
            "allocation_row_count": len(allocation_rows),
            "allocation_rows_sha256": document_rows_sha256(
                allocation_rows,
                row_kind="allocations",
            ),
            "byte_length": len(raw),
            "exclusion_row_count": len(exclusion_rows),
            "exclusion_rows_sha256": document_rows_sha256(
                exclusion_rows,
                row_kind="exclusions",
            ),
            "modules": module_rows,
            "path": relative_path,
            "sha256": sha256(raw).hexdigest(),
            "source_set": copy.deepcopy(ADR_SOURCE_SET_SUITE),
        }
        document_row["source_set"]["sha256"] = adr_source_set_sha256(
            adr_id=adr_id,
            path=relative_path,
            byte_length=len(raw),
            source_sha256=document_row["sha256"],
            modules=module_rows,
        )
        document_rows.append(document_row)

    model = _model_allocations(data)
    declared_model = {
        ModelAllocation(
            row["kind"],
            row["exact_name"],
            row["semantic_ref"],
        )
        for row in inventory_allocations
    }
    external_names = set().union(*external_identifiers.values())
    unreachable_state_rows = _selector_unreachable_state_rows(data)
    (
        states_without_terminal_path,
        terminal_escape_transitions,
    ) = _selector_terminal_liveness_rows(data)
    observer_request_product_liveness_rows = (
        _observer_grant_request_product_liveness_rows(data)
    )
    observer_request_causal_liveness = (
        _observer_grant_request_causal_liveness_diagnostic(data)
    )
    gap_rows: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    for allocation in sorted(model - declared_model):
        kind = allocation.kind
        exact_name = allocation.exact_name
        semantic_ref = allocation.semantic_ref
        prose_adr_ids = sorted(
            adr_id
            for adr_id, tokens in prose_identifier_tokens.items()
            if exact_name in tokens
        )
        accepted_prose_adr_ids = sorted(
            adr_id
            for adr_id, tokens in accepted_prose_identifiers.items()
            if exact_name in tokens
        )
        if (
            kind == "STATE"
            and semantic_ref.removeprefix("state-id::") in unreachable_state_rows
        ):
            status = "MODEL_REPAIR_REQUIRED_UNREACHABLE_STATE"
        elif accepted_prose_adr_ids:
            status = "EXTERNAL_INVENTORY_ADDITION_CANDIDATE"
        else:
            status = "ADR_SEMANTIC_REVIEW_REQUIRED_BEFORE_ADDITION"
        status_counts[status] = status_counts.get(status, 0) + 1
        gap_rows.append(
            {
                "accepted_prose_adr_ids": accepted_prose_adr_ids,
                "exact_name": exact_name,
                "kind": kind,
                "origins": allocation.evidence_row()["origins"],
                "prose_adr_ids": prose_adr_ids,
                "semantic_ref": semantic_ref,
                "signals": allocation.evidence_row()["signals"],
                "status": status,
                "unit_id": allocation.unit_id,
            }
        )

    artifacts = set(data["artifacts"])
    missing_artifact_refs = sorted(_semantic_artifact_references(data) - artifacts)
    registered_artifact_refs_by_exact_name: dict[str, list[str]] = {}
    for reference in sorted(artifacts):
        registered_artifact_refs_by_exact_name.setdefault(
            reference.split("::", 1)[1], []
        ).append(reference)
    registerable_missing_artifact_refs = missing_artifact_refs
    selector_reference_sets = {
        selector["selector_id"]: set(_iter_string_values(selector))
        for selector in data["selectors"]
    }
    artifact_omissions = []
    projected_model = set(model)
    for reference in missing_artifact_refs:
        referencing_selectors = sorted(
            selector_id
            for selector_id, references in selector_reference_sets.items()
            if reference in references
        )
        matching_units = [
            allocation for allocation in model if allocation.semantic_ref == reference
        ]
        projected_kind = matching_units[0].kind if len(matching_units) == 1 else "TYPE"
        artifact_omissions.append(
            {
                "exact_name": reference.split("::", 1)[1],
                "kind": projected_kind,
                "referencing_selector_ids": referencing_selectors,
                "registered_refs_with_same_exact_name": (
                    registered_artifact_refs_by_exact_name.get(
                        reference.split("::", 1)[1], []
                    )
                ),
                "semantic_ref": reference,
                "status": "MODEL_ALLOCATION_OMISSION_ARTIFACT_NOT_REGISTERED",
            }
        )
        if not matching_units:
            projected_model.add(
                ModelAllocation(
                    "TYPE",
                    reference.split("::", 1)[1],
                    reference,
                )
            )

    status_priority = (
        "MODEL_REPAIR_REQUIRED_UNREACHABLE_STATE",
        "ADR_SEMANTIC_REVIEW_REQUIRED_BEFORE_ADDITION",
        "EXTERNAL_INVENTORY_ADDITION_CANDIDATE",
    )
    statuses_by_name: dict[str, set[str]] = {}
    for row in gap_rows:
        statuses_by_name.setdefault(row["exact_name"], set()).add(row["status"])
    name_status_counts = {
        status: sum(
            1
            for statuses in statuses_by_name.values()
            if next(candidate for candidate in status_priority if candidate in statuses)
            == status
        )
        for status in status_priority
    }

    candidate_rows_by_pair: dict[ExtractedIdentifier, list[ModelAllocation]] = {}
    for allocation in projected_model:
        adr_id = _candidate_allocation_adr_id(
            allocation,
            accepted_prose_identifiers=accepted_prose_identifiers,
        )
        candidate_rows_by_pair.setdefault((adr_id, allocation.exact_name), []).append(
            allocation
        )
    current_identifier_pairs = {
        (adr_id, exact_name)
        for adr_id, exact_names in external_identifiers.items()
        for exact_name in exact_names
    }
    candidate_gap_pairs = set(candidate_rows_by_pair) - current_identifier_pairs
    candidate_gap_rows: list[dict[str, Any]] = []
    candidate_gap_class_counts: dict[str, int] = {}
    candidate_gap_class_counts_by_adr: dict[str, dict[str, int]] = {}
    missing_artifact_ref_set = set(missing_artifact_refs)
    for adr_id, exact_name in sorted(candidate_gap_pairs):
        allocations = sorted(candidate_rows_by_pair[(adr_id, exact_name)])
        accepted_prose_adr_ids = sorted(
            candidate_adr_id
            for candidate_adr_id, identifiers in accepted_prose_identifiers.items()
            if exact_name in identifiers
        )
        external_inventory_adr_ids = sorted(
            candidate_adr_id
            for candidate_adr_id, identifiers in external_identifiers.items()
            if exact_name in identifiers
        )
        prose_adr_ids = sorted(
            candidate_adr_id
            for candidate_adr_id, identifiers in prose_identifier_tokens.items()
            if exact_name in identifiers
        )
        noninventory_prose_adr_ids = sorted(
            set(prose_adr_ids) - set(external_inventory_adr_ids)
        )
        if adr_id == "UNMAPPED_SHARED":
            classification = "UNMAPPED_SHARED_REVIEW_REQUIRED"
        elif any(
            allocation.semantic_ref in missing_artifact_ref_set
            for allocation in allocations
        ):
            classification = "ARTIFACT_REGISTRY_MODEL_REPAIR"
        elif any(
            allocation.kind == "STATE"
            and allocation.semantic_ref.removeprefix("state-id::")
            in unreachable_state_rows
            for allocation in allocations
        ):
            classification = "UNREACHABLE_STATE_MODEL_REPAIR"
        elif exact_name in accepted_prose_identifiers[adr_id]:
            classification = "EXTERNAL_INVENTORY_ONLY"
        else:
            classification = "ADR_SEMANTIC_REVIEW_REQUIRED"
        if accepted_prose_adr_ids:
            provenance_signal = "EXACT_NAME_IN_ACCEPTED_SECTION_OF_OTHER_ADR"
        elif noninventory_prose_adr_ids:
            provenance_signal = "NONACCEPTED_PROSE_MENTION"
        elif external_inventory_adr_ids:
            provenance_signal = "INVENTORY_IN_OTHER_ADR_ONLY"
        else:
            provenance_signal = "NO_ADR_PROSE_OR_INVENTORY_OCCURRENCE"
        candidate_gap_class_counts[classification] = (
            candidate_gap_class_counts.get(classification, 0) + 1
        )
        adr_counts = candidate_gap_class_counts_by_adr.setdefault(adr_id, {})
        adr_counts[classification] = adr_counts.get(classification, 0) + 1
        candidate_gap_rows.append(
            {
                "accepted_prose_adr_ids": accepted_prose_adr_ids,
                "adr_id": adr_id,
                "classification": classification,
                "exact_name": exact_name,
                "model_rows": [row.evidence_row() for row in allocations],
                "noninventory_prose_adr_ids": (noninventory_prose_adr_ids),
                "external_inventory_adr_ids": external_inventory_adr_ids,
                "prose_adr_ids": prose_adr_ids,
                "provenance_signal": provenance_signal,
            }
        )

    document_by_adr = {document["adr_id"]: document for document in document_rows}
    candidate_gap_names_by_adr: dict[str, list[str]] = {
        adr_id: sorted(
            exact_name
            for candidate_adr_id, exact_name in candidate_gap_pairs
            if candidate_adr_id == adr_id
        )
        for adr_id in external_identifiers
    }
    candidate_adr_summaries = {}
    for adr_id, names in candidate_gap_names_by_adr.items():
        current_bytes = document_by_adr[adr_id]["byte_length"]
        candidate_adr_summaries[adr_id] = {
            "candidate_gap_class_counts": {
                key: candidate_gap_class_counts_by_adr.get(adr_id, {}).get(key, 0)
                for key in sorted(candidate_gap_class_counts)
            },
            "candidate_gap_identifier_count": len(names),
            "current_byte_headroom": MAX_ADR_BYTES - current_bytes,
            "current_byte_length": current_bytes,
            "current_external_identifier_count": len(external_identifiers[adr_id]),
            "literal_inventory_bytes_added_to_adr": 0,
        }
    unmapped_shared_gap_rows = [
        row for row in candidate_gap_rows if row["adr_id"] == "UNMAPPED_SHARED"
    ]

    final_candidate_identifier_pairs = current_identifier_pairs | candidate_gap_pairs
    candidate_allocation_pairs = set(candidate_rows_by_pair)
    candidate_capacity_projection = _candidate_capacity_projection(
        data,
        accepted_prose_identifiers=accepted_prose_identifiers,
        current_document_rows=document_rows,
        registerable_missing_artifact_refs=(registerable_missing_artifact_refs),
    )
    _verify_adr_snapshots_unchanged(snapshots)
    return {
        "artifact_registry_entry_count": len(artifacts),
        "artifact_registry_missing_registration_refs": (
            registerable_missing_artifact_refs
        ),
        "artifact_registry_unused_entries": sorted(
            artifacts - _semantic_artifact_references(data)
        ),
        "claim_boundary": (
            "READ_ONLY_MOVING_CORPUS_DIAGNOSTIC_NOT_AN_ALLOCATION_"
            "FREEZE_OR_COMPLETENESS_RESULT"
        ),
        "artifact_registration_projection_claim_boundary": (
            "EXACT_SEMANTIC_REFERENCE_REGISTRY_ADDITIONS_ONLY_NOT_AN_"
            "ALLOCATION_OR_RELEASE_RESULT"
        ),
        "artifact_registration_projection_model_allocation_count": len(projected_model),
        "artifact_registration_projection_model_allocation_sha256": (
            _model_allocation_sha256(projected_model)
        ),
        "artifact_registration_projection_model_distinct_name_count": len(
            {row.exact_name for row in projected_model}
        ),
        "artifact_registration_projection_globally_absent_exact_name_count": len(
            {row.exact_name for row in projected_model} - external_names
        ),
        "candidate_assignment_plan": {
            "allocation_identifier_pair_count": len(candidate_allocation_pairs),
            "claim_boundary": ("REVIEW_SUGGESTION_ONLY_NOT_ORACLE_AUTHORITY_OR_FREEZE"),
            "final_identifier_pair_count": len(final_candidate_identifier_pairs),
            "gap_class_counts": {
                key: candidate_gap_class_counts[key]
                for key in sorted(candidate_gap_class_counts)
            },
            "gap_identifier_pair_count": len(candidate_gap_pairs),
            "gap_rows": candidate_gap_rows,
            "per_adr": candidate_adr_summaries,
            "semantic_review_summary": (
                _candidate_semantic_review_summary(candidate_gap_rows)
            ),
            "unmapped_shared_identifier_pair_count": len(unmapped_shared_gap_rows),
            "unmapped_shared_unit_ids": sorted(
                {
                    model_row["unit_id"]
                    for row in unmapped_shared_gap_rows
                    for model_row in row["model_rows"]
                }
            ),
            "projected_typed_exclusion_pair_count": len(
                final_candidate_identifier_pairs - candidate_allocation_pairs
            ),
        },
        "candidate_storage_capacity_projection": (candidate_capacity_projection),
        "decision_relation_coverage_diagnostic": (
            _decision_relation_coverage_diagnostic(data)
        ),
        "documents": document_rows,
        "globally_absent_exact_name_count": len(
            {row["exact_name"] for row in gap_rows}
        ),
        "lifecycle_analysis_claim_boundary": (
            "STRUCTURAL_STATE_GRAPH_PATH_AND_TERMINAL_ABSORPTION_ONLY_"
            "NOT_SCHEDULING_FAIRNESS_DURATION_OR_EXTERNAL_QUALIFICATION"
        ),
        "model_allocation_count": len(model),
        "model_allocation_sha256": _model_allocation_sha256(model),
        "model_origin_signal_projection_schema": (
            MODEL_ORIGIN_SIGNAL_PROJECTION_SCHEMA
        ),
        "model_origin_signal_row_count": _model_origin_signal_commitment(model)[0],
        "model_origin_signal_sha256": _model_origin_signal_commitment(model)[1],
        "model_distinct_name_count": len({row.exact_name for row in model}),
        "model_allocation_omissions": artifact_omissions,
        "model_rows_without_exact_external_inventory_row": gap_rows,
        "model_rows_without_exact_external_inventory_row_count": len(gap_rows),
        "name_status_counts": name_status_counts,
        "observer_grant_request_product_claim_boundary": (
            "KIND_REFINED_SINGLE_EXACT_REQUEST_KEY_NECESSARY_CONDITION_"
            "LINT_A_PASS_PROVES_NO_MULTI_KEY_REACHABILITY_SCHEDULING_"
            "FAIRNESS_DURATION_NETWORK_OR_EXTERNAL_QUALIFICATION"
        ),
        "observer_grant_request_causal_liveness_diagnostic": (
            observer_request_causal_liveness
        ),
        "observer_grant_request_product_states_without_terminal_path": (
            observer_request_product_liveness_rows
        ),
        "status_counts": {key: status_counts[key] for key in sorted(status_counts)},
        "states_without_terminal_path": sorted(states_without_terminal_path),
        "terminal_state_escape_transitions": sorted(terminal_escape_transitions),
        "unreachable_state_model_refs": sorted(unreachable_state_rows),
    }


def _validate_profile_references(data: dict[str, Any]) -> None:
    catalog = data["closed_event_profile_catalog"]
    mappings = {
        "candidate_constraints_profile_ref": "candidate_constraints",
        "guards_profile_ref": "guards",
        "interruption_resolutions_profile_ref": "interruption_resolutions",
        "operation_commitment_profile_ref": "operation_commitment",
        "security_serialization_profile_ref": "security_serialization",
        "version_effects_profile_ref": "version_effects",
    }
    profile_ids = {
        field: {profile["profile_id"] for profile in catalog[category]}
        for field, category in mappings.items()
    }
    sidecar_profiles = {
        profile_id
        for profile_id in data["sidecar_binding_profiles"]
        if SEMANTIC_ID.fullmatch(profile_id) is not None
    }
    used_profile_ids = {field: set() for field in mappings}
    used_sidecar_profiles: set[str] = set()
    for selector in data["selectors"]:
        for event in selector["events"]:
            label = f"{selector['selector_id']}.{event['event_id']}"
            for field in mappings:
                require(
                    event[field] in profile_ids[field],
                    f"{label}: dangling {field} {event[field]!r}",
                )
                used_profile_ids[field].add(event[field])
            for sidecar in event["post_cas_sidecars"]:
                require(
                    sidecar["binding_profile_ref"] in sidecar_profiles,
                    (
                        f"{label}: dangling sidecar binding profile "
                        f"{sidecar['binding_profile_ref']!r}"
                    ),
                )
                used_sidecar_profiles.add(sidecar["binding_profile_ref"])
    for field in mappings:
        require_exact(
            used_profile_ids[field],
            profile_ids[field],
            f"closed event catalog {field} definition/use surface",
        )
    require_exact(
        used_sidecar_profiles,
        sidecar_profiles,
        "sidecar binding profile definition/use surface",
    )


def _selector_indexes(
    data: dict[str, Any],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[tuple[str, str], dict[str, Any]],
    dict[tuple[str, str], dict[str, Any]],
]:
    selectors = data["selectors"]
    selector_by_id = {selector["selector_id"]: selector for selector in selectors}
    event_by_key = {
        (selector["selector_id"], event["event_id"]): event
        for selector in selectors
        for event in selector["events"]
    }
    domain_by_key = {
        (selector["selector_id"], state_domain["state_domain"]): state_domain
        for selector in selectors
        for state_domain in selector["state_domains"]
    }
    return selector_by_id, event_by_key, domain_by_key


def _validate_artifact_ref(
    reference: Any,
    artifacts: set[str],
    label: str,
) -> None:
    require(
        isinstance(reference, str) and ALLOCATION_REF.fullmatch(reference),
        f"{label}: invalid allocation reference {reference!r}",
    )
    require(reference in artifacts, f"{label}: unregistered {reference!r}")


def _validate_handoff_quiescence_bijections(
    data: dict[str, Any],
    artifacts: set[str],
) -> None:
    expected_events = {
        "APPLY_OBSERVER_SECURITY_REBOUND_OR_REVOCATION_CUT",
        "OBSERVER_AUTHORIZATION_CLOCK_RESTART",
        "REPLACE_OBSERVER_DESCRIPTOR_OR_PRIVACY",
        "RETIRE_OBSERVER_SESSION_GENERATION",
    }
    expected_contract = {
        "admitted_record_branch": "ADMITTED_RECORD_TO_TERMINAL",
        "missing_duplicate_unknown_or_unproved_fence": ("REJECT_WITHOUT_STATE_CHANGE"),
        "result_set_root": (
            "observer-grant-paired-challenge-frame-handoff-quiescence-"
            "result-set-root-type::"
            "ObserverGrantPairedChallengeFrameHandoffQuiescenceResultSetRoot"
        ),
        "rule": (
            "EXACTLY_ONE_QUALIFIED_CLOSED_RESULT_AND_PROOF_PER_ADMITTED_"
            "RECORD_BEFORE_ANY_TERMINALIZING_CAS"
        ),
    }
    expected_proof_root = (
        "observer-grant-paired-challenge-frame-handoff-quiescence-"
        "proof-set-root-type::"
        "ObserverGrantPairedChallengeFrameHandoffQuiescenceProofSetRoot"
    )
    expected_binding = (
        "ADMITTED_RECORD_PARTITION_HAS_EXACT_BIJECTION_TO_ONE_HANDOFF_"
        "QUIESCENCE_RESULT_AND_PROOF_PER_RECORD"
    )
    occurrences: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for selector in data["selectors"]:
        for event in selector["events"]:
            for partition in event["partition_effects"]:
                contract = partition.get("handoff_quiescence_bijection")
                if contract is None:
                    continue
                label = (
                    f"{selector['selector_id']}.{event['event_id']}."
                    f"{partition['partition_id']}.handoff_quiescence_bijection"
                )
                require_exact(
                    selector["selector_id"],
                    "OBSERVER_AUTHORIZATION",
                    f"{label}: selector",
                )
                require_exact(
                    partition["partition_id"],
                    "P004",
                    f"{label}: partition",
                )
                require_exact(
                    partition["state_domain"],
                    "PAIRED_CHALLENGE_FRAME_ADMISSION_RECORD",
                    f"{label}: state domain",
                )
                require_exact(contract, expected_contract, f"{label}: contract")
                _validate_artifact_ref(
                    contract["result_set_root"],
                    artifacts,
                    f"{label}.result_set_root",
                )
                branch = next(
                    (
                        item
                        for item in partition["branches"]
                        if item["branch_id"] == contract["admitted_record_branch"]
                    ),
                    None,
                )
                require(branch is not None, f"{label}: admitted branch is absent")
                require_exact(
                    (branch["from_state"], branch["to_state"]),
                    ("ADMITTED", "TERMINAL"),
                    f"{label}: admitted branch transition",
                )
                payloads = [
                    item
                    for item in event["atomic_pre_cas_payloads"]
                    if item["artifact"] == contract["result_set_root"]
                ]
                require_exact(
                    len(payloads),
                    1,
                    f"{label}: result-set payload count",
                )
                payload = payloads[0]
                require_exact(
                    payload["bound_by"],
                    expected_proof_root,
                    f"{label}: proof-set root",
                )
                _validate_artifact_ref(
                    payload["bound_by"],
                    artifacts,
                    f"{label}: proof-set root",
                )
                require_exact(
                    payload["constructed"],
                    (
                        "AFTER_EXCLUSIVE_DISPATCH_TOKEN_ACQUISITION_AND_BEFORE_"
                        "THE_TERMINALIZING_CANDIDATE_SUCCESSOR"
                    ),
                    f"{label}: construction point",
                )
                require_exact(
                    payload["exposure"],
                    "ONLY_AS_RECEIPT_FREE_PRE_CAS_QUIESCENCE_EVIDENCE",
                    f"{label}: exposure",
                )
                require_exact(
                    payload["persistence"],
                    "WITH_AUTHORITY_DOMAIN_TRANSACTION",
                    f"{label}: persistence",
                )
                require_exact(
                    payload["role"],
                    "EXACT_COMPLETE_ADMITTED_RECORD_CLOSED_RESULT_SET",
                    f"{label}: role",
                )
                require(
                    set(partition["applies_to_semantic_case_ids"]).issubset(
                        payload["applies_to_semantic_case_ids"]
                    ),
                    f"{label}: payload omits an applicable semantic case",
                )
                require(
                    expected_binding in event["pre_cas_content"]["required_bindings"],
                    f"{label}: pre-CAS bijection binding is absent",
                )
                require(
                    event["event_id"] not in occurrences,
                    f"{label}: duplicate event occurrence",
                )
                occurrences[event["event_id"]] = (partition, payload)
    require_exact(
        set(occurrences),
        expected_events,
        "observer handoff-quiescence bijection event surface",
    )


def _reachable_states(
    initial_state: str,
    transitions: set[tuple[str, str]],
) -> set[str]:
    reachable = {initial_state}
    while True:
        successor = reachable | {
            target for source, target in transitions if source in reachable
        }
        if successor == reachable:
            return reachable
        reachable = successor


def _validate_domain_state_reachability(
    *,
    selector_id: str,
    state_domains: list[dict[str, Any]],
    transitions_by_domain: dict[str, set[tuple[str, str]]],
    allow_known_incomplete: bool,
) -> None:
    """Reject declared states that no modeled transition can ever install."""

    unreachable_rows = _unreachable_state_rows(
        selector_id=selector_id,
        state_domains=state_domains,
        transitions_by_domain=transitions_by_domain,
    )
    if allow_known_incomplete:
        return
    require(
        not unreachable_rows,
        (
            f"{selector_id}: declared states are unreachable from their "
            "domain initial state through the closed edge and partition "
            f"surface: count={len(unreachable_rows)} "
            f"sample={unreachable_rows[:3]}"
        ),
    )


def _unreachable_state_rows(
    *,
    selector_id: str,
    state_domains: list[dict[str, Any]],
    transitions_by_domain: dict[str, set[tuple[str, str]]],
) -> list[str]:
    unreachable_rows: list[str] = []
    for state_domain in state_domains:
        domain_id = state_domain["state_domain"]
        reachable = _reachable_states(
            state_domain["initial_state"],
            transitions_by_domain[domain_id],
        )
        unreachable_rows.extend(
            f"{selector_id}.{domain_id}.{state}"
            for state in sorted(set(state_domain["states"]) - reachable)
        )
    return unreachable_rows


def _terminal_liveness_rows(
    *,
    selector_id: str,
    state_domains: list[dict[str, Any]],
    transitions_by_domain: dict[str, set[tuple[str, str]]],
) -> tuple[list[str], list[str]]:
    """Return nonterminating states and transitions that escape terminal state."""

    states_without_terminal_path: list[str] = []
    terminal_escape_transitions: list[str] = []
    for state_domain in state_domains:
        domain_id = state_domain["state_domain"]
        transitions = transitions_by_domain[domain_id]
        terminal_states = set(state_domain["terminal_states"])
        if state_domain["terminality"] == "ALL_REACH_TERMINAL":
            can_reach_terminal = set(terminal_states)
            while True:
                predecessor_closure = can_reach_terminal | {
                    source
                    for source, target in transitions
                    if target in can_reach_terminal
                }
                if predecessor_closure == can_reach_terminal:
                    break
                can_reach_terminal = predecessor_closure
            states_without_terminal_path.extend(
                f"{selector_id}.{domain_id}.{state}"
                for state in sorted(set(state_domain["states"]) - can_reach_terminal)
            )
        terminal_escape_transitions.extend(
            (f"{selector_id}.{domain_id}.{source}->{target}")
            for source, target in sorted(transitions)
            if source in terminal_states and target not in terminal_states
        )
    return states_without_terminal_path, terminal_escape_transitions


def _validate_domain_terminal_liveness(
    *,
    selector_id: str,
    state_domains: list[dict[str, Any]],
    transitions_by_domain: dict[str, set[tuple[str, str]]],
    allow_known_incomplete: bool,
) -> None:
    """Require declared terminal progress and immutable terminal states."""

    if allow_known_incomplete:
        return
    (
        states_without_terminal_path,
        terminal_escape_transitions,
    ) = _terminal_liveness_rows(
        selector_id=selector_id,
        state_domains=state_domains,
        transitions_by_domain=transitions_by_domain,
    )
    require(
        not states_without_terminal_path,
        (
            f"{selector_id}: ALL_REACH_TERMINAL states lack a modeled "
            f"terminal path: count={len(states_without_terminal_path)} "
            f"sample={states_without_terminal_path[:3]}"
        ),
    )
    require(
        not terminal_escape_transitions,
        (
            f"{selector_id}: declared terminal states have resurrection "
            f"transitions: count={len(terminal_escape_transitions)} "
            f"sample={terminal_escape_transitions[:3]}"
        ),
    )


def _run_domain_state_reachability_self_test() -> int:
    state_domains = [
        {
            "initial_state": "ABSENT",
            "state_domain": "ENTRY",
            "states": ["ABSENT", "LIVE", "TERMINAL"],
            "terminal_states": ["TERMINAL"],
            "terminality": "ALL_REACH_TERMINAL",
        }
    ]
    complete_transitions = {"ENTRY": {("ABSENT", "LIVE"), ("LIVE", "TERMINAL")}}
    _validate_domain_state_reachability(
        selector_id="SYNTHETIC",
        state_domains=state_domains,
        transitions_by_domain=complete_transitions,
        allow_known_incomplete=False,
    )
    _validate_domain_terminal_liveness(
        selector_id="SYNTHETIC",
        state_domains=state_domains,
        transitions_by_domain=complete_transitions,
        allow_known_incomplete=False,
    )
    try:
        _validate_domain_state_reachability(
            selector_id="SYNTHETIC",
            state_domains=state_domains,
            transitions_by_domain={"ENTRY": {("LIVE", "TERMINAL")}},
            allow_known_incomplete=False,
        )
    except ClosureCheckError:
        pass
    else:
        fail("state reachability self-test accepted an unreachable state")
    for hostile_transitions, label in (
        (
            {"ENTRY": {("ABSENT", "LIVE"), ("TERMINAL", "TERMINAL")}},
            "nonterminal dead end",
        ),
        (
            {
                "ENTRY": {
                    ("ABSENT", "LIVE"),
                    ("LIVE", "TERMINAL"),
                    ("TERMINAL", "LIVE"),
                }
            },
            "terminal resurrection",
        ),
    ):
        try:
            _validate_domain_terminal_liveness(
                selector_id="SYNTHETIC",
                state_domains=state_domains,
                transitions_by_domain=hostile_transitions,
                allow_known_incomplete=False,
            )
        except ClosureCheckError:
            pass
        else:
            fail(f"state liveness self-test accepted {label}")
    return 3


def _run_request_partition_contract_self_test() -> int:
    """Reject kind-erased bulk resolution and permissive finalization."""

    preserve_edges = OBSERVER_GRANT_REQUEST_IMPORT_PRESERVE_BRANCH_STATES
    branches = [
        {
            "branch_id": branch_id,
            "from_state": "INTENT_PREPARED",
            "to_state": "RESOLVED_WITHOUT_INSTALLATION",
        }
        for branch_id in OBSERVER_GRANT_PERMANENT_RESOLUTION_CAUSE_BY_PARTITION_BRANCH
    ] + [
        {
            "branch_id": branch_id,
            "from_state": state,
            "to_state": state,
        }
        for branch_id, state in preserve_edges.items()
    ]
    resolution_rows = [
        dict(
            zip(
                (
                    "branch_id",
                    "causal_outcome",
                    "from_local_state",
                    "g0_closure_requirement",
                    "request_kind",
                    "to_local_state",
                ),
                row,
                strict=True,
            )
        )
        for row in sorted(_expected_request_kind_product_resolution_rows())
    ]
    partition = {
        "branches": branches,
        "partition_id": "P002",
        "request_kind_product_contract": {
            "causal_outcome_source": (
                "VERIFIER_DERIVED_FROM_BRANCH_EXACT_PROOF_NOT_CALLER_LABEL"
            ),
            "kind_field": OBSERVER_GRANT_REQUEST_KIND_FIELD,
            "kind_source": "VERIFIED_RETAINED_OPERATION_STABLE_KEY",
            "operation_edge_source": "EXACT_PARTITION_BRANCH_FROM_AND_TO_STATE",
            "outer_state_rule": "PRESERVE_EXACT_INSTALLED_OUTER_STATE",
            "preserve_branch_kind_scopes": [
                {
                    "branch_id": branch_id,
                    "request_kinds": sorted(OBSERVER_GRANT_REQUEST_KINDS),
                }
                for branch_id in sorted(preserve_edges)
            ],
            "resolution_rows": resolution_rows,
            "unknown_missing_duplicate_or_cross_kind": ("REJECT_WITHOUT_STATE_CHANGE"),
        },
        "state_domain": "OBSERVER_GRANT_REQUEST_OPERATION_STATE",
    }
    import_event = {
        "event_id": OBSERVER_GRANT_SOURCE_NAMESPACE_CLOSURE_IMPORT_EVENT,
    }
    require_exact(
        len(
            _validate_request_kind_product_partition_contract(
                event=import_event,
                partition=partition,
            )
        ),
        9,
        "request-kind partition self-test baseline row count",
    )

    rejected = 0

    def expect_partition_rejection(
        mutate: Any,
        *,
        label: str,
    ) -> None:
        nonlocal rejected
        hostile = copy.deepcopy(partition)
        mutate(hostile)
        try:
            _validate_request_kind_product_partition_contract(
                event=import_event,
                partition=hostile,
            )
        except ClosureCheckError:
            rejected += 1
        else:
            fail(f"request-kind partition self-test accepted {label}")

    expect_partition_rejection(
        lambda hostile: hostile["request_kind_product_contract"][
            "resolution_rows"
        ].pop(),
        label="a missing branch/kind row",
    )
    expect_partition_rejection(
        lambda hostile: hostile["request_kind_product_contract"]["resolution_rows"][
            0
        ].__setitem__("causal_outcome", "CALLER_SELECTED_CAUSE"),
        label="a caller-selected causal outcome",
    )
    expect_partition_rejection(
        lambda hostile: hostile["request_kind_product_contract"]["resolution_rows"][
            0
        ].__setitem__("from_local_state", "LIVE"),
        label="a cross-kind local state",
    )
    renew_row_index = next(
        index
        for index, row in enumerate(resolution_rows)
        if row["request_kind"] == "RENEW"
    )
    expect_partition_rejection(
        lambda hostile: hostile["request_kind_product_contract"]["resolution_rows"][
            renew_row_index
        ].__setitem__(
            "g0_closure_requirement",
            "TYPED_INAPPLICABLE",
        ),
        label="RENEW without exact G0 closure",
    )
    expect_partition_rejection(
        lambda hostile: hostile["request_kind_product_contract"][
            "preserve_branch_kind_scopes"
        ][0]["request_kinds"].pop(),
        label="a kind-erased preserve branch",
    )
    expect_partition_rejection(
        lambda hostile: hostile["branches"][0].__setitem__(
            "from_state",
            "PENDING_RESPONSE",
        ),
        label="a mismatched resolving operation edge",
    )

    terminal_contract = {
        "observer_grant_request_target_profile": {
            "request_product_terminal_contract": {
                "causal_states_by_operation_state": {
                    "ABSENT": [OBSERVER_GRANT_REQUEST_INITIAL_CAUSAL_STATE],
                    "INSTALLED": ["LIVE_RESPONSE"],
                    "RESOLVED_WITHOUT_INSTALLATION": sorted(
                        {
                            "ACCEPTED_TERMINAL_PENDING_AGGREGATES",
                            "SERVER_SLOT_CANCELED_UNUSED",
                            "SERVER_SLOT_EXPIRED_UNUSED",
                            *OBSERVER_GRANT_PREPARED_INTENT_PERMANENT_RESOLUTION_CAUSES,
                        }
                    ),
                },
                "local_state": "TERMINAL",
                "operation_states": sorted(
                    OBSERVER_GRANT_REQUEST_TERMINAL_OPERATION_STATES
                ),
                "outer_state": "TERMINAL",
                "predicate": "EXACT_CONTEXTUAL_PRODUCT_TERMINAL_SET",
                "unknown_default_or_mismatch": "NOT_TERMINAL",
            }
        }
    }
    _request_product_terminal_contract(terminal_contract)
    for field, value in (
        ("operation_states", ["ABSENT", "PENDING_RESPONSE"]),
        (
            "causal_states_by_operation_state",
            {
                "ABSENT": ["LIVE_RESPONSE"],
                "INSTALLED": ["LIVE_RESPONSE"],
                "RESOLVED_WITHOUT_INSTALLATION": [],
            },
        ),
    ):
        hostile = copy.deepcopy(terminal_contract)
        hostile["observer_grant_request_target_profile"][
            "request_product_terminal_contract"
        ][field] = value
        try:
            _request_product_terminal_contract(hostile)
        except ClosureCheckError:
            rejected += 1
        else:
            fail(
                "request-kind partition self-test accepted a permissive "
                f"context-terminal {field}"
            )

    finalization_event = {
        "event_id": OBSERVER_GRANT_REQUEST_FINALIZATION_EVENT,
        "operation_scope": "BOUNDED_KEY_SET",
        "pre_cas_content": {
            "required_bindings": [
                "EVERY_REQUEST_OPERATION_HAS_EXACTLY_ONE_TERMINAL_RESOLUTION"
            ]
        },
        "request_product_finalization_guard": {
            "coverage": "EXACT_DISJOINT_COMPLETE_OPERATION_KEY_PARTITION",
            "operation_state_domain": "OBSERVER_GRANT_REQUEST_OPERATION_STATE",
            "preservation": "BYTE_IDENTICAL_EVERY_OPERATION_ENTRY",
            "required_exact_states": sorted(
                OBSERVER_GRANT_REQUEST_TERMINAL_OPERATION_STATES
            ),
            "unknown_missing_duplicate_or_nonterminal": ("REJECT_WITHOUT_STATE_CHANGE"),
        },
        "transition_cases": [
            {"semantic_case_id": "FINALIZE_FENCED"},
            {"semantic_case_id": "FINALIZE_RETIRED"},
        ],
    }
    _request_product_finalization_guard_states(finalization_event)
    for mutation, label in (
        (
            lambda hostile: hostile["request_product_finalization_guard"][
                "required_exact_states"
            ].append("PENDING_RESPONSE"),
            "pending operation in the finalization guard",
        ),
        (
            lambda hostile: hostile.pop("request_product_finalization_guard"),
            "missing finalization guard",
        ),
    ):
        hostile = copy.deepcopy(finalization_event)
        mutation(hostile)
        try:
            _request_product_finalization_guard_states(hostile)
        except ClosureCheckError:
            rejected += 1
        else:
            fail(f"request-kind partition self-test accepted {label}")

    operation_key_type = (
        "observer-admission-observer-grant-request-operation-state-key-type::"
        "ObserverAdmissionObserverGrantRequestOperationStateKey"
    )
    finalization_partition = {
        "applies_to_semantic_case_ids": [
            "FINALIZE_FENCED",
            "FINALIZE_RETIRED",
        ],
        "bijection": "EXACTLY_ONE_BRANCH_AND_OUTCOME_PER_OPERATION_KEY",
        "branches": [
            {
                "branch_id": "ABSENT_PRESERVED",
                "cardinality": "ZERO_OR_MORE_BOUNDED_KEYS",
                "entry_effect": "PRESERVE_VALIDATE_ONLY",
                "from_state": "ABSENT",
                "key_mode": "PARTITION",
                "key_partition": (
                    "CANONICAL_COMPLETE_UNUSED_REQUEST_OPERATION_KEY_SET"
                ),
                "key_ref": operation_key_type,
                "to_state": "ABSENT",
                "version_effect": "UNCHANGED",
            },
            {
                "branch_id": "INSTALLED_PRESERVED",
                "cardinality": "ZERO_OR_MORE_BOUNDED_KEYS",
                "entry_effect": "PRESERVE_VALIDATE_ONLY",
                "from_state": "INSTALLED",
                "key_mode": "PARTITION",
                "key_partition": (
                    "CANONICAL_COMPLETE_INSTALLED_REQUEST_OPERATION_KEY_SET"
                ),
                "key_ref": operation_key_type,
                "to_state": "INSTALLED",
                "version_effect": "UNCHANGED",
            },
            {
                "branch_id": "RESOLVED_WITHOUT_INSTALLATION_PRESERVED",
                "cardinality": "ZERO_OR_MORE_BOUNDED_KEYS",
                "entry_effect": "PRESERVE_VALIDATE_ONLY",
                "from_state": "RESOLVED_WITHOUT_INSTALLATION",
                "key_mode": "PARTITION",
                "key_partition": (
                    "CANONICAL_COMPLETE_RESOLVED_WITHOUT_INSTALLATION_"
                    "REQUEST_OPERATION_KEY_SET"
                ),
                "key_ref": operation_key_type,
                "to_state": "RESOLVED_WITHOUT_INSTALLATION",
                "version_effect": "UNCHANGED",
            },
        ],
        "coverage": "EXACT_DISJOINT_COMPLETE_OPERATION_KEY_PARTITION",
        "empty_partitions": "PERMITTED_AND_EXPLICIT",
        "inventory_semantics": (
            "EXACT_COMPLETE_MANIFEST_BOUNDED_REQUEST_OPERATION_KEY_UNIVERSE"
        ),
        "key_type": operation_key_type,
        "missing_extra_duplicate_or_nonterminal": "REJECT_WITHOUT_STATE_CHANGE",
        "partition_id": "P001",
        "preserve_unlisted_keys": True,
    }
    _validate_request_product_finalization_partition_contract(
        event=finalization_event,
        partition=finalization_partition,
        operation_key_type=operation_key_type,
        required_states=set(OBSERVER_GRANT_REQUEST_TERMINAL_OPERATION_STATES),
    )
    for mutation, label in (
        (
            lambda hostile: hostile["branches"].pop(),
            "incomplete finalization operation partition",
        ),
        (
            lambda hostile: hostile["branches"][0].__setitem__(
                "entry_effect",
                "TOMBSTONE",
            ),
            "mutating finalization operation partition",
        ),
    ):
        hostile = copy.deepcopy(finalization_partition)
        mutation(hostile)
        try:
            _validate_request_product_finalization_partition_contract(
                event=finalization_event,
                partition=hostile,
                operation_key_type=operation_key_type,
                required_states=set(OBSERVER_GRANT_REQUEST_TERMINAL_OPERATION_STATES),
            )
        except ClosureCheckError:
            rejected += 1
        else:
            fail(f"request-kind partition self-test accepted {label}")
    return rejected


def _run_request_product_liveness_self_test() -> int:
    initial_state = ("PENDING", "PENDING_RESPONSE")
    cut_transition = (
        initial_state,
        ("PREDECESSOR_CLOSED", "PENDING_RESPONSE"),
    )
    resolver_transition = (
        ("PREDECESSOR_CLOSED", "PENDING_RESPONSE"),
        ("PREDECESSOR_CLOSED", "RESOLVED"),
    )
    retirement_transition = (
        ("PREDECESSOR_CLOSED", "RESOLVED"),
        ("RETIRED", "RESOLVED"),
    )
    terminal_states = {("RETIRED", "RESOLVED")}
    complete_transitions = {
        cut_transition,
        resolver_transition,
        retirement_transition,
    }
    require(
        not _product_states_without_terminal_path(
            initial_state=initial_state,
            transitions=complete_transitions,
            terminal_states=terminal_states,
        ),
        "request-product self-test rejected a complete closure",
    )

    try:
        require(
            not _product_states_without_terminal_path(
                initial_state=initial_state,
                transitions={cut_transition, retirement_transition},
                terminal_states=terminal_states,
            ),
            "synthetic request product has a stranded nonterminal state",
        )
    except ClosureCheckError:
        pass
    else:
        fail("request-product self-test accepted a missing same-kind resolver")

    kind_scoped_transitions = {
        "ATTACH": {cut_transition, retirement_transition},
        "RENEW": {resolver_transition},
    }
    require(
        not _product_states_without_terminal_path(
            initial_state=initial_state,
            transitions=set().union(*kind_scoped_transitions.values()),
            terminal_states=terminal_states,
        ),
        "request-product self-test fixture lacks a naive union path",
    )
    try:
        require(
            not _product_states_without_terminal_path(
                initial_state=initial_state,
                transitions=kind_scoped_transitions["ATTACH"],
                terminal_states=terminal_states,
            ),
            "synthetic request product borrowed a wrong-kind resolver",
        )
    except ClosureCheckError:
        pass
    else:
        fail("request-product self-test accepted a wrong-kind resolver")
    return 2


def _run_request_causal_liveness_self_test() -> int:
    unknown = OBSERVER_GRANT_REQUEST_INITIAL_CAUSAL_STATE
    live = "LIVE_RESPONSE"
    accepted = "ACCEPTED_TERMINAL_PENDING_AGGREGATES"
    canceled = "SERVER_SLOT_CANCELED_UNUSED"
    require_exact(
        _observer_grant_request_case_causal_edges(
            event_id="INSTALL_OBSERVER_GRANT_FROM_ACCEPTED_RESPONSE",
            evidence_variant_id="SYNTHETIC",
        ),
        frozenset({(unknown, live), (live, live)}),
        "request-causal install compatibility",
    )
    observation_edges = _observer_grant_request_case_causal_edges(
        event_id=OBSERVER_GRANT_REQUEST_TERMINAL_OBSERVATION_EVENT,
        evidence_variant_id="SYNTHETIC",
    )
    require_exact(
        observation_edges,
        frozenset(
            {
                (unknown, accepted),
                (accepted, accepted),
                (live, accepted),
            }
        ),
        "request-causal terminal observation monotonicity",
    )
    require(
        all(target != canceled for _, target in observation_edges),
        "request-causal terminal observation permits LIVE-to-unused",
    )
    require_exact(
        _observer_grant_request_case_causal_edges(
            event_id=("RESOLVE_OBSERVER_GRANT_ATTACH_REQUEST_WITHOUT_INSTALLATION"),
            evidence_variant_id="SERVER_SLOT_CANCELED_UNUSED",
            resolution_cause="SERVER_SLOT_CANCELED_UNUSED",
        ),
        frozenset({(unknown, canceled), (canceled, canceled)}),
        "request-causal unused resolver compatibility",
    )
    require_exact(
        _observer_grant_request_case_causal_edges(
            event_id=("RESOLVE_OBSERVER_GRANT_ATTACH_REQUEST_WITHOUT_INSTALLATION"),
            evidence_variant_id="AMBIGUOUS_COMBINED_CAUSE",
        ),
        frozenset(),
        "request-causal ambiguous resolver rejection",
    )
    require_exact(
        _observer_grant_request_case_causal_edges(
            event_id=("RESOLVE_OBSERVER_GRANT_ATTACH_REQUEST_WITHOUT_INSTALLATION"),
            evidence_variant_id="SERVER_SLOT_CANCELED_UNUSED",
        ),
        frozenset(),
        "request-causal cause label cannot self-certify",
    )

    erased_initial = ("OPEN", "PENDING_RESPONSE")
    erased_cut = (
        erased_initial,
        ("DENY", "PENDING_RESPONSE"),
    )
    erased_wrong_cause_resolver = (
        ("DENY", "PENDING_RESPONSE"),
        ("DENY", "RESOLVED"),
    )
    erased_retirement = (
        ("DENY", "RESOLVED"),
        ("TERMINAL", "RESOLVED"),
    )
    require(
        not _product_states_without_terminal_path(
            initial_state=erased_initial,
            transitions={
                erased_cut,
                erased_wrong_cause_resolver,
                erased_retirement,
            },
            terminal_states={("TERMINAL", "RESOLVED")},
        ),
        "request-causal self-test fixture lacks a cause-erased path",
    )

    refined_initial = (*erased_initial, live)
    refined_cut = (
        refined_initial,
        ("DENY", "PENDING_RESPONSE", live),
    )
    refined_wrong_cause_resolver = (
        ("DENY", "PENDING_RESPONSE", canceled),
        ("DENY", "RESOLVED", canceled),
    )
    refined_retirement = (
        ("DENY", "RESOLVED", canceled),
        ("TERMINAL", "RESOLVED", canceled),
    )
    try:
        require(
            not _product_states_without_terminal_path(
                initial_state=refined_initial,
                transitions={
                    refined_cut,
                    refined_wrong_cause_resolver,
                    refined_retirement,
                },
                terminal_states={
                    ("TERMINAL", "RESOLVED", canceled),
                    ("TERMINAL", "RESOLVED", live),
                },
            ),
            "synthetic request product borrowed an unused-slot resolver",
        )
    except ClosureCheckError:
        pass
    else:
        fail("request-causal self-test accepted cross-cause borrowing")

    refined_observation = (
        ("DENY", "PENDING_RESPONSE", live),
        ("DENY", "TERMINAL_RESULT_OBSERVED", accepted),
    )
    refined_accepted_resolver = (
        ("DENY", "TERMINAL_RESULT_OBSERVED", accepted),
        ("DENY", "RESOLVED", accepted),
    )
    refined_accepted_retirement = (
        ("DENY", "RESOLVED", accepted),
        ("TERMINAL", "RESOLVED", accepted),
    )
    require(
        not _product_states_without_terminal_path(
            initial_state=refined_initial,
            transitions={
                refined_cut,
                refined_observation,
                refined_accepted_resolver,
                refined_accepted_retirement,
            },
            terminal_states={
                ("TERMINAL", "RESOLVED", accepted),
            },
        ),
        "request-causal self-test rejected LIVE-to-accepted closure",
    )
    return 7


def _run_request_evidence_contract_self_test() -> int:
    def evidence_variant(
        *,
        exact_values: dict[str, str] | None = None,
        variant_id: str,
        required_fields: set[str],
        forbidden_fields: set[str],
    ) -> dict[str, Any]:
        exact_values = exact_values or {}
        truth_conditions = [
            {
                "field": field,
                "operator": (
                    OBSERVER_GRANT_ACTIVATION_PUBLICATION_MANIFEST_OPERATOR
                    if field == OBSERVER_GRANT_ACTIVATION_PUBLICATION_MANIFEST_FIELD
                    else (
                        "EQUALS"
                        if field in exact_values
                        else "VERIFIES_EXACT_PROTECTED_EVIDENCE"
                    )
                ),
                "value": (exact_values[field] if field in exact_values else True),
            }
            for field in sorted(required_fields)
        ]
        return {
            "evidence_variant_id": variant_id,
            "forbidden_fields": sorted(forbidden_fields),
            "required_fields": sorted(required_fields),
            "truth_conditions": truth_conditions,
        }

    def event(
        event_id: str,
        event_variants: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "decision_model": {
                "common_required_fields": [],
                "evidence_variant_definitions": event_variants,
            },
            "event_id": event_id,
        }

    observation_fields = set(OBSERVER_GRANT_REQUEST_OBSERVATION_EVIDENCE_FIELDS)
    accepted_fields = set(OBSERVER_GRANT_REQUEST_ACCEPTED_CLOSURE_EVIDENCE_FIELDS)
    unused_fields = set(OBSERVER_GRANT_REQUEST_UNUSED_EVIDENCE_FIELDS)
    events = []
    for event_id in (
        OBSERVER_GRANT_REQUEST_AMBIGUITY_EVENT,
        OBSERVER_GRANT_REQUEST_PREPARE_EVENT,
    ):
        events.append(
            event(
                event_id,
                [
                    evidence_variant(
                        exact_values={OBSERVER_GRANT_REQUEST_KIND_FIELD: kind},
                        variant_id=f"{kind}_TYPED_EVENT_FACT_VALIDATED",
                        required_fields={OBSERVER_GRANT_REQUEST_KIND_FIELD},
                        forbidden_fields=set(),
                    )
                    for kind in sorted(OBSERVER_GRANT_REQUEST_KINDS)
                ],
            )
        )
    events.append(
        event(
            OBSERVER_GRANT_REQUEST_TERMINAL_OBSERVATION_EVENT,
            [
                evidence_variant(
                    exact_values={OBSERVER_GRANT_REQUEST_KIND_FIELD: kind},
                    variant_id=(f"{kind}_PROTECTED_TERMINAL_RESULT_OBSERVED"),
                    required_fields=observation_fields
                    | {OBSERVER_GRANT_REQUEST_KIND_FIELD},
                    forbidden_fields=accepted_fields,
                )
                for kind in sorted(OBSERVER_GRANT_REQUEST_KINDS)
            ],
        )
    )
    intent_forbidden_fields = accepted_fields | (
        set(OBSERVER_GRANT_REQUEST_INSTALL_EVIDENCE_FIELDS)
        - {OBSERVER_GRANT_REQUEST_VERIFICATION_FIELD}
    )
    intent_required_base = {
        OBSERVER_GRANT_REQUEST_EXACT_INTENT_FIELD,
        OBSERVER_GRANT_REQUEST_INTENT_CAUSE_FIELD,
        OBSERVER_GRANT_REQUEST_KIND_FIELD,
        OBSERVER_GRANT_REQUEST_VERIFICATION_FIELD,
        *unused_fields,
    }
    events.append(
        event(
            OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT,
            [
                evidence_variant(
                    exact_values={
                        OBSERVER_GRANT_REQUEST_INTENT_CAUSE_FIELD: cause,
                        OBSERVER_GRANT_REQUEST_KIND_FIELD: kind,
                    },
                    variant_id=f"{kind}_{cause}",
                    required_fields=intent_required_base,
                    forbidden_fields=intent_forbidden_fields,
                )
                for kind in sorted(OBSERVER_GRANT_REQUEST_KINDS)
                for cause in (
                    "SERVER_SLOT_CANCELED_UNUSED",
                    "SERVER_SLOT_EXPIRED_UNUSED",
                )
            ],
        )
    )
    install_forbidden_fields = accepted_fields | unused_fields
    for event_id in sorted(OBSERVER_GRANT_REQUEST_INSTALL_EVENTS):
        events.append(
            event(
                event_id,
                [
                    evidence_variant(
                        variant_id="PROTECTED_LIVE_RESPONSE_VERIFIED",
                        required_fields=(
                            set(OBSERVER_GRANT_REQUEST_INSTALL_EVIDENCE_FIELDS)
                            | set(
                                OBSERVER_GRANT_REQUEST_INSTALL_ADDITIONAL_EVIDENCE_FIELDS[
                                    event_id
                                ]
                            )
                        ),
                        forbidden_fields=install_forbidden_fields,
                    )
                ],
            )
        )
    common_resolver_fields = {
        OBSERVER_GRANT_REQUEST_CAUSE_FIELD,
        OBSERVER_GRANT_REQUEST_EXACT_ATTEMPT_FIELD,
        OBSERVER_GRANT_REQUEST_VERIFICATION_FIELD,
    }
    for event_id in sorted(OBSERVER_GRANT_REQUEST_RESOLVER_EVENTS):
        event_variants = []
        for cause in sorted(OBSERVER_GRANT_REQUEST_TERMINAL_RESOLUTION_CAUSES):
            is_accepted = cause == (
                "ACCEPTED_GRANT_FULLY_CLOSED_WITHOUT_LOCAL_INSTALLATION"
            )
            event_variants.append(
                evidence_variant(
                    exact_values={OBSERVER_GRANT_REQUEST_CAUSE_FIELD: cause},
                    variant_id=cause,
                    required_fields=(
                        common_resolver_fields
                        | (accepted_fields if is_accepted else unused_fields)
                    ),
                    forbidden_fields=(
                        unused_fields if is_accepted else accepted_fields
                    ),
                )
            )
        events.append(event(event_id, event_variants))
    selector = {"events": events}
    evidence_issues = _observer_grant_request_evidence_contract_issues(selector)
    require(
        not evidence_issues,
        (
            "request-evidence self-test rejected a complete disjoint "
            f"contract: {evidence_issues}"
        ),
    )

    missing_required = copy.deepcopy(selector)
    observation_variant = next(
        item
        for item in missing_required["events"]
        if item["event_id"] == OBSERVER_GRANT_REQUEST_TERMINAL_OBSERVATION_EVENT
    )["decision_model"]["evidence_variant_definitions"][0]
    observation_variant["required_fields"].remove(
        OBSERVER_GRANT_REQUEST_EXACT_ATTEMPT_FIELD
    )
    observation_variant["truth_conditions"] = [
        condition
        for condition in observation_variant["truth_conditions"]
        if condition["field"] != OBSERVER_GRANT_REQUEST_EXACT_ATTEMPT_FIELD
    ]
    require(
        _observer_grant_request_evidence_contract_issues(missing_required),
        "request-evidence self-test accepted a missing protected input",
    )

    false_cause = copy.deepcopy(selector)
    resolver_event = next(
        item
        for item in false_cause["events"]
        if item["event_id"] in OBSERVER_GRANT_REQUEST_RESOLVER_EVENTS
    )
    accepted_variant = next(
        item
        for item in resolver_event["decision_model"]["evidence_variant_definitions"]
        if item["evidence_variant_id"]
        == "ACCEPTED_GRANT_FULLY_CLOSED_WITHOUT_LOCAL_INSTALLATION"
    )
    cause_condition = next(
        condition
        for condition in accepted_variant["truth_conditions"]
        if condition["field"] == OBSERVER_GRANT_REQUEST_CAUSE_FIELD
    )
    cause_condition["value"] = "SERVER_SLOT_CANCELED_UNUSED"
    require(
        _observer_grant_request_evidence_contract_issues(false_cause),
        "request-evidence self-test accepted a self-asserted wrong cause",
    )

    overlapping_branch = copy.deepcopy(selector)
    resolver_event = next(
        item
        for item in overlapping_branch["events"]
        if item["event_id"] in OBSERVER_GRANT_REQUEST_RESOLVER_EVENTS
    )
    accepted_variant = next(
        item
        for item in resolver_event["decision_model"]["evidence_variant_definitions"]
        if item["evidence_variant_id"]
        == "ACCEPTED_GRANT_FULLY_CLOSED_WITHOUT_LOCAL_INSTALLATION"
    )
    accepted_variant["forbidden_fields"].remove(sorted(unused_fields)[0])
    require(
        _observer_grant_request_evidence_contract_issues(overlapping_branch),
        "request-evidence self-test accepted overlapping cause branches",
    )

    missing_activation_manifest = copy.deepcopy(selector)
    install_event = next(
        item
        for item in missing_activation_manifest["events"]
        if item["event_id"] in OBSERVER_GRANT_REQUEST_INSTALL_EVENTS
    )
    install_variant = install_event["decision_model"]["evidence_variant_definitions"][0]
    install_variant["required_fields"].remove(
        OBSERVER_GRANT_ACTIVATION_PUBLICATION_MANIFEST_FIELD
    )
    install_variant["truth_conditions"] = [
        condition
        for condition in install_variant["truth_conditions"]
        if condition["field"] != OBSERVER_GRANT_ACTIVATION_PUBLICATION_MANIFEST_FIELD
    ]
    require(
        _observer_grant_request_evidence_contract_issues(missing_activation_manifest),
        "request-evidence self-test accepted an unmanifested LIVE response",
    )

    unbound_activation_manifest = copy.deepcopy(selector)
    install_event = next(
        item
        for item in unbound_activation_manifest["events"]
        if item["event_id"] in OBSERVER_GRANT_REQUEST_INSTALL_EVENTS
    )
    manifest_condition = next(
        condition
        for condition in install_event["decision_model"][
            "evidence_variant_definitions"
        ][0]["truth_conditions"]
        if condition["field"] == OBSERVER_GRANT_ACTIVATION_PUBLICATION_MANIFEST_FIELD
    )
    manifest_condition["operator"] = "IS_PRESENT"
    require(
        _observer_grant_request_evidence_contract_issues(unbound_activation_manifest),
        (
            "request-evidence self-test accepted a manifest without exact "
            "activation membership/bijection"
        ),
    )

    kind_erased_intent_resolution = copy.deepcopy(selector)
    intent_event = next(
        item
        for item in kind_erased_intent_resolution["events"]
        if item["event_id"] == OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT
    )
    intent_variant = intent_event["decision_model"]["evidence_variant_definitions"][0]
    intent_variant["truth_conditions"] = [
        condition
        for condition in intent_variant["truth_conditions"]
        if condition["field"] != OBSERVER_GRANT_REQUEST_KIND_FIELD
    ]
    require(
        _observer_grant_request_evidence_contract_issues(kind_erased_intent_resolution),
        (
            "request-evidence self-test accepted a kind-erased prepared "
            "intent resolution"
        ),
    )
    return 6


def _run_cross_store_publication_manifest_self_test() -> int:
    def event(
        *,
        event_id: str,
        exact_operators: dict[str, str],
        required_fields: set[str],
    ) -> dict[str, Any]:
        return {
            "decision_model": {
                "common_required_fields": [],
                "evidence_variant_definitions": [
                    {
                        "evidence_variant_id": "EXACT_PROTECTED_BUNDLE",
                        "forbidden_fields": [],
                        "required_fields": sorted(required_fields),
                        "truth_conditions": [
                            {
                                "field": field,
                                "operator": exact_operators.get(
                                    field,
                                    (CROSS_STORE_EXACT_OPERATION_VERIFICATION_OPERATOR),
                                ),
                                "value": True,
                            }
                            for field in sorted(required_fields)
                        ],
                    }
                ],
            },
            "event_id": event_id,
        }

    activation_fields = {
        CROSS_STORE_PRODUCER_COMPLETION_MANIFEST_FIELD,
        CROSS_STORE_PROTECTED_OUTPUT_DELIVERY_CAPSULE_FIELD,
        OBSERVER_GRANT_REQUEST_VERIFICATION_FIELD,
        TRUSTED_DELIVERY_BOUNDARY_ACTIVATION_ENVELOPE_FIELD,
        TRUSTED_DELIVERY_BOUNDARY_ACTIVATION_MANIFEST_FIELD,
    }
    closure_fields = {
        CROSS_STORE_PRODUCER_COMPLETION_MANIFEST_FIELD,
        CROSS_STORE_PROTECTED_OUTPUT_DELIVERY_CAPSULE_FIELD,
        OBSERVER_GRANT_REQUEST_VERIFICATION_FIELD,
        TRUSTED_DELIVERY_BOUNDARY_CLOSURE_ENVELOPE_FIELD,
        TRUSTED_DELIVERY_BOUNDARY_CLOSURE_MANIFEST_FIELD,
    }
    boundary_artifacts = sorted(
        OBSERVER_GRANT_CLOSURE_AGGREGATION_BOUNDARY_PUBLICATION_ARTIFACTS
    )

    def aggregation_arm(*, consumes_boundary_return: bool) -> dict[str, Any]:
        return {
            "forbidden_fields": (
                [] if consumes_boundary_return else boundary_artifacts.copy()
            ),
            "required_fields": (
                boundary_artifacts.copy() if consumes_boundary_return else []
            ),
        }

    def aggregation_variant(
        *,
        variant_id: str,
        input_kind: str,
    ) -> dict[str, Any]:
        empty = input_kind == "EXACT_EMPTY_ACCEPTED_PLAN"
        branch_field = (
            OBSERVER_GRANT_CLOSURE_AGGREGATION_EMPTY_UNIVERSE_PROOF_FIELD
            if empty
            else OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_EVIDENCE_BIJECTION_FIELD
        )
        opposite_field = (
            OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_EVIDENCE_BIJECTION_FIELD
            if empty
            else OBSERVER_GRANT_CLOSURE_AGGREGATION_EMPTY_UNIVERSE_PROOF_FIELD
        )
        branch_operator = (
            "BINDS_EMPTY_UNIVERSE"
            if empty
            else OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_BIJECTION_OPERATOR
        )
        return {
            "evidence_variant_id": variant_id,
            "forbidden_fields": sorted({opposite_field, *closure_fields}),
            "required_fields": [
                OBSERVER_GRANT_CLOSURE_AGGREGATION_EVIDENCE_INPUT_FIELD,
                branch_field,
            ],
            "truth_conditions": [
                {
                    "field": (OBSERVER_GRANT_CLOSURE_AGGREGATION_EVIDENCE_INPUT_FIELD),
                    "operator": "CLOSED_UNION_VARIANT_EQUALS",
                    "value": input_kind,
                },
                {
                    "field": branch_field,
                    "operator": branch_operator,
                    "value": True,
                },
            ],
        }

    aggregation_event = {
        "decision_model": {
            "common_required_fields": [],
            "evidence_variant_definitions": [
                aggregation_variant(
                    variant_id="MEMBER_BATCH",
                    input_kind="MEMBER_ADVANCE_BATCH",
                ),
                aggregation_variant(
                    variant_id="EMPTY",
                    input_kind="EXACT_EMPTY_ACCEPTED_PLAN",
                ),
            ],
        },
        "event_id": OBSERVER_GRANT_CLOSURE_AGGREGATION_EVENT,
    }
    authorization_test_arms = {
        arm_id: aggregation_arm(
            consumes_boundary_return=arm_id
            in {
                "NO_INSTALL_ZERO_WORK_PROVED",
                "TERMINAL_ACKED",
            }
        )
        for arm_id in (
            "BOUNDARY_PERMANENTLY_ISOLATED_WITH_COMPLETE_EXACT_WORK_PARTITION",
            "BOUNDARY_PERMANENTLY_ISOLATED_WITH_UNKNOWN_RETAINED_WORK",
            "DEADLINE_ELAPSED_UNACKNOWLEDGED_WITH_UNKNOWN_RETAINED_WORK",
            "NO_INSTALL_ZERO_WORK_PROVED",
            "SERVER_TERMINAL_FROM_PENDING_NEVER_LIVE",
            "TERMINAL_ACKED",
        )
    }
    transport_test_arms = {
        arm_id: aggregation_arm(
            consumes_boundary_return=arm_id
            in {
                "EMERGENCY_COMPLETE_CLOSURE_TRANSPORT_QUIESCENT",
                "TERMINAL_ENTRY_TRANSPORT_QUIESCENT",
            }
        )
        for arm_id in (
            "EMERGENCY_COMPLETE_CLOSURE_TRANSPORT_QUIESCENT",
            "NO_INSTALL_ZERO_ITEMS",
            "PERMANENT_ISOLATION_ZERO_ITEMS",
            "SERVER_TERMINAL_FROM_PENDING_NEVER_LIVE_ZERO_ITEMS",
            "TERMINAL_ENTRY_TRANSPORT_QUIESCENT",
        )
    }
    data = {
        "observer_grant_request_target_profile": {
            "closure_aggregation_contract": {
                "evidence_input": {
                    "member_advance_batch": {
                        "per_member_authorization_origin": {
                            "native_union_arms": authorization_test_arms
                        },
                        "per_member_transport_origin": {
                            "native_union_arms": transport_test_arms
                        },
                    }
                }
            }
        },
        "selectors": [
            {
                "events": [aggregation_event],
                "selector_id": "OBSERVER_ATTACHMENT_TARGET_HISTORY",
            },
            {
                "events": [
                    event(
                        event_id=(TRUSTED_DELIVERY_BOUNDARY_ACTIVATION_EVENT),
                        exact_operators={
                            TRUSTED_DELIVERY_BOUNDARY_ACTIVATION_MANIFEST_FIELD: (
                                TRUSTED_DELIVERY_BOUNDARY_ACTIVATION_MANIFEST_OPERATOR
                            )
                        },
                        required_fields=activation_fields,
                    )
                ],
                "selector_id": "TRUSTED_DELIVERY_RELEASE",
            },
        ],
    }
    issues = _cross_store_publication_manifest_contract_issues(data)
    require(
        not issues,
        (
            "cross-store publication self-test rejected complete manifest "
            f"contracts: {issues}"
        ),
    )

    mutants = []
    for selector_id, event_id, required_fields in (
        (
            "TRUSTED_DELIVERY_RELEASE",
            TRUSTED_DELIVERY_BOUNDARY_ACTIVATION_EVENT,
            activation_fields,
        ),
    ):
        for field in sorted(required_fields):
            missing = copy.deepcopy(data)
            target_event = next(
                event
                for selector in missing["selectors"]
                if selector["selector_id"] == selector_id
                for event in selector["events"]
                if event["event_id"] == event_id
            )
            variant = target_event["decision_model"]["evidence_variant_definitions"][0]
            variant["required_fields"].remove(field)
            variant["truth_conditions"] = [
                condition
                for condition in variant["truth_conditions"]
                if condition["field"] != field
            ]
            mutants.append(
                (
                    missing,
                    f"{selector_id} accepted missing cross-store field {field}",
                )
            )

            unbound = copy.deepcopy(data)
            target_event = next(
                event
                for selector in unbound["selectors"]
                if selector["selector_id"] == selector_id
                for event in selector["events"]
                if event["event_id"] == event_id
            )
            condition = next(
                condition
                for condition in target_event["decision_model"][
                    "evidence_variant_definitions"
                ][0]["truth_conditions"]
                if condition["field"] == field
            )
            condition["operator"] = "IS_PRESENT"
            mutants.append(
                (
                    unbound,
                    f"{selector_id} accepted unbound cross-store field {field}",
                )
            )

            false_verification = copy.deepcopy(data)
            target_event = next(
                event
                for selector in false_verification["selectors"]
                if selector["selector_id"] == selector_id
                for event in selector["events"]
                if event["event_id"] == event_id
            )
            condition = next(
                condition
                for condition in target_event["decision_model"][
                    "evidence_variant_definitions"
                ][0]["truth_conditions"]
                if condition["field"] == field
            )
            condition["value"] = False
            mutants.append(
                (
                    false_verification,
                    f"{selector_id} accepted false cross-store field {field}",
                )
            )

    authorization_boundary_arms = {
        "NO_INSTALL_ZERO_WORK_PROVED",
        "TERMINAL_ACKED",
    }
    transport_boundary_arms = {
        "EMERGENCY_COMPLETE_CLOSURE_TRANSPORT_QUIESCENT",
        "TERMINAL_ENTRY_TRANSPORT_QUIESCENT",
    }

    def aggregation_arms(
        document: dict[str, Any],
        family: str,
    ) -> dict[str, dict[str, Any]]:
        member_batch = document["observer_grant_request_target_profile"][
            "closure_aggregation_contract"
        ]["evidence_input"]["member_advance_batch"]
        return member_batch[
            (
                "per_member_authorization_origin"
                if family == "AUTHORIZATION"
                else "per_member_transport_origin"
            )
        ]["native_union_arms"]

    for family, boundary_arm_ids in (
        ("AUTHORIZATION", authorization_boundary_arms),
        ("TRANSPORT", transport_boundary_arms),
    ):
        for arm_id, arm in aggregation_arms(data, family).items():
            for artifact in boundary_artifacts:
                hostile = copy.deepcopy(data)
                hostile_arm = aggregation_arms(hostile, family)[arm_id]
                field = (
                    "required_fields"
                    if arm_id in boundary_arm_ids
                    else "forbidden_fields"
                )
                hostile_arm[field].remove(artifact)
                mutants.append(
                    (
                        hostile,
                        (
                            "aggregation accepted "
                            f"{family}.{arm_id} without exact {field} {artifact}"
                        ),
                    )
                )

    for variant_index in range(2):
        for field in sorted(closure_fields):
            hostile = copy.deepcopy(data)
            hostile_event = next(
                item
                for selector in hostile["selectors"]
                if selector["selector_id"] == "OBSERVER_ATTACHMENT_TARGET_HISTORY"
                for item in selector["events"]
            )
            hostile_event["decision_model"]["evidence_variant_definitions"][
                variant_index
            ]["forbidden_fields"].remove(field)
            mutants.append(
                (
                    hostile,
                    (
                        "aggregation accepted ambiguous top-level publication "
                        f"field {field}"
                    ),
                )
            )

    weak_member_bijection = copy.deepcopy(data)
    weak_event = next(
        item
        for selector in weak_member_bijection["selectors"]
        if selector["selector_id"] == "OBSERVER_ATTACHMENT_TARGET_HISTORY"
        for item in selector["events"]
    )
    member_variant = weak_event["decision_model"]["evidence_variant_definitions"][0]
    member_condition = next(
        condition
        for condition in member_variant["truth_conditions"]
        if condition["field"]
        == OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_EVIDENCE_BIJECTION_FIELD
    )
    member_condition["operator"] = "IS_PRESENT"
    mutants.append(
        (
            weak_member_bijection,
            "aggregation accepted an unverified member evidence bijection",
        )
    )

    singular_bundle = copy.deepcopy(data)
    singular_event = next(
        item
        for selector in singular_bundle["selectors"]
        if selector["selector_id"] == "OBSERVER_ATTACHMENT_TARGET_HISTORY"
        for item in selector["events"]
    )
    singular_variant = singular_event["decision_model"]["evidence_variant_definitions"][
        0
    ]
    singular_field = TRUSTED_DELIVERY_BOUNDARY_CLOSURE_ENVELOPE_FIELD
    singular_variant["forbidden_fields"].remove(singular_field)
    singular_variant["required_fields"].append(singular_field)
    singular_variant["truth_conditions"].append(
        {
            "field": singular_field,
            "operator": CROSS_STORE_EXACT_OPERATION_VERIFICATION_OPERATOR,
            "value": True,
        }
    )
    mutants.append(
        (
            singular_bundle,
            "aggregation accepted one singular envelope for a member batch",
        )
    )

    for mutant, label in mutants:
        require(
            _cross_store_publication_manifest_contract_issues(mutant),
            f"cross-store publication self-test {label}",
        )
    return len(mutants)


def _run_observer_grant_closure_aggregation_self_test(
    baseline: dict[str, Any],
) -> int:
    """Require hostile lattice, output, authority, and DAG mutations to fail."""

    _validate_observer_grant_closure_aggregation_contract(baseline)

    def selector(data: dict[str, Any]) -> dict[str, Any]:
        return next(
            item
            for item in data["selectors"]
            if item["selector_id"] == "OBSERVER_ATTACHMENT_TARGET_HISTORY"
        )

    def event(data: dict[str, Any]) -> dict[str, Any]:
        return next(
            item
            for item in selector(data)["events"]
            if item["event_id"] == OBSERVER_GRANT_CLOSURE_AGGREGATION_EVENT
        )

    def domain(data: dict[str, Any]) -> dict[str, Any]:
        return next(
            item
            for item in selector(data)["state_domains"]
            if item["state_domain"] == OBSERVER_GRANT_CLOSURE_AGGREGATION_DOMAIN
        )

    def profile_contract(data: dict[str, Any]) -> dict[str, Any]:
        return data["observer_grant_request_target_profile"][
            "closure_aggregation_contract"
        ]

    def sidecar(data: dict[str, Any], artifact_name: str) -> dict[str, Any]:
        return next(
            item
            for item in event(data)["post_cas_sidecars"]
            if artifact_name in item["artifact"]
        )

    def evidence_variant(
        data: dict[str, Any],
        variant_id: str,
    ) -> dict[str, Any]:
        return next(
            item
            for item in event(data)["decision_model"]["evidence_variant_definitions"]
            if item["evidence_variant_id"] == variant_id
        )

    def consume(data: dict[str, Any], artifact_name: str) -> dict[str, Any]:
        return next(
            item
            for item in event(data)["consumes"]
            if artifact_name in item["artifact"]
        )

    mutants: list[tuple[str, Any]] = []
    mutants.append(
        (
            "untyped aggregation head",
            lambda data: profile_contract(data)["head"].__setitem__(
                "type",
                "observer-grant-closure-aggregation-head-identity::PermissiveAlias",
            ),
        )
    )
    mutants.append(
        (
            "unknown member counted as transport-quiescent",
            lambda data: profile_contract(data)[
                "aggregate_output_derivation"
            ].__setitem__(
                "TRANSPORT_QUIESCENT",
                "EVERY_MEMBER_IS_AUTH_CLOSED_UNKNOWN_OR_TRANSPORT_QUIESCENT",
            ),
        )
    )
    mutants.append(
        (
            "kind-erased aggregation operation key",
            lambda data: profile_contract(data)["idempotency"]["key_coordinates"].pop(),
        )
    )
    mutants.append(
        (
            "non-atomic aggregation head update",
            lambda data: profile_contract(data)["head"].__setitem__(
                "update",
                "BEST_EFFORT_SUCCESSOR_HEAD",
            ),
        )
    )
    mutants.append(
        (
            "repeatable empty-universe successor operation",
            lambda data: profile_contract(data)["head"].__setitem__(
                "empty_universe_successor_or_second_operation",
                "ALLOW_ANOTHER_EMPTY_SUCCESSOR",
            ),
        )
    )
    mutants.append(
        (
            "caller-selected aggregation operation coordinate",
            lambda data: profile_contract(data)["idempotency"][
                "key_coordinates"
            ].append("CALLER_OPERATION_ID"),
        )
    )
    mutants.append(
        (
            "grant-renewal-ambiguous operation key",
            lambda data: profile_contract(data)["idempotency"][
                "key_coordinates"
            ].remove("OBSERVER_GRANT_ISSUANCE_SEQUENCE"),
        )
    )
    mutants.append(
        (
            "branch-specific evidence root erased",
            lambda data: profile_contract(data)["idempotency"].__setitem__(
                "evidence_input_commitment_root",
                "GENERIC_UNTYPED_EVIDENCE_SET_ROOT",
            ),
        )
    )
    mutants.append(
        (
            "empty plan admits one affected member",
            lambda data: profile_contract(data)["evidence_input"][
                "exact_empty_accepted_plan"
            ].__setitem__("affected_member_count", 1),
        )
    )
    mutants.append(
        (
            "empty plan accepts boundary member evidence",
            lambda data: profile_contract(data)["evidence_input"][
                "exact_empty_accepted_plan"
            ]["forbidden_fields"].remove("BOUNDARY_CLOSURE_EVIDENCE_ENVELOPE"),
        )
    )
    mutants.append(
        (
            "native authorization union arm accepts mixed evidence",
            lambda data: profile_contract(data)["evidence_input"][
                "member_advance_batch"
            ]["per_member_authorization_origin"]["native_union_arms"]["TERMINAL_ACKED"][
                "forbidden_fields"
            ].pop(),
        )
    )
    mutants.append(
        (
            "transport evidence drops prior-unknown ancestry",
            lambda data: profile_contract(data)["evidence_input"][
                "member_advance_batch"
            ]["per_member_transport_origin"].__setitem__(
                "rule",
                "CURRENT_EXACT_AUTHORIZATION_MEMBER_ONLY",
            ),
        )
    )
    mutants.append(
        (
            "shared publication manifest treated as one-to-one member evidence",
            lambda data: profile_contract(data)["evidence_input"][
                "member_advance_batch"
            ].__setitem__(
                "shared_publication_hierarchy",
                "ONE_MANIFEST_PER_MEMBER",
            ),
        )
    )
    mutants.append(
        (
            "mutable source index redefines the member universe",
            lambda data: profile_contract(data)["member_universe"].__setitem__(
                "authority",
                "CURRENT_MUTABLE_SOURCE_INDEX",
            ),
        )
    )
    mutants.append(
        (
            "missing AUTH_CLOSED_UNKNOWN lattice state",
            lambda data: domain(data)["states"].remove("AUTH_CLOSED_UNKNOWN"),
        )
    )

    def add_unknown_to_quiescent(data: dict[str, Any]) -> None:
        partition = event(data)["partition_effects"][0]
        hostile = copy.deepcopy(partition["branches"][0])
        hostile["branch_id"] = "AUTH_CLOSED_UNKNOWN_TO_TRANSPORT_QUIESCENT"
        hostile["from_state"] = "AUTH_CLOSED_UNKNOWN"
        hostile["to_state"] = "TRANSPORT_QUIESCENT"
        partition["branches"].append(hostile)

    mutants.append(("UNKNOWN-to-quiescent lattice jump", add_unknown_to_quiescent))
    mutants.append(
        (
            "regressive exact-to-unknown lattice edge",
            lambda data: event(data)["partition_effects"][0]["branches"][0].__setitem__(
                "to_state", "UNOBSERVED"
            ),
        )
    )
    mutants.append(
        (
            "non-tombstoned terminal lattice edge",
            lambda data: event(data)["partition_effects"][0]["branches"][
                -1
            ].__setitem__("entry_effect", "MUTATE"),
        )
    )

    def add_scalar_lattice_escape(data: dict[str, Any]) -> None:
        selector(data)["state_edge_catalog"].append(
            {
                "edge_id": "HOSTILE_SCALAR_AGGREGATION_ESCAPE",
                "entry_effect": "MUTATE",
                "from_state": "UNOBSERVED",
                "key_cardinality": "EXACT_ONE_KEY",
                "key_mode": "EXACT_KEY",
                "key_ref": OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_KEY,
                "preserve_siblings": True,
                "state_domain": OBSERVER_GRANT_CLOSURE_AGGREGATION_DOMAIN,
                "to_state": "AUTH_CLOSED_UNKNOWN",
            }
        )

    mutants.append(("scalar lattice escape", add_scalar_lattice_escape))

    def require_nonempty_common_member_write(data: dict[str, Any]) -> None:
        member_effect = next(
            item
            for item in event(data)["common_case_effects"]
            if item["resource"].endswith(
                f"STATE_DOMAIN.{OBSERVER_GRANT_CLOSURE_AGGREGATION_DOMAIN}"
            )
        )
        member_effect["cardinality"] = "ONE_OR_MORE_BOUNDED_KEYS"

    mutants.append(
        (
            "empty-universe branch forced to write a member",
            require_nonempty_common_member_write,
        )
    )
    mutants.append(
        (
            "member partition branch forbids explicit emptiness",
            lambda data: event(data)["partition_effects"][0]["branches"][0].__setitem__(
                "cardinality", "ONE_OR_MORE_BOUNDED_KEYS"
            ),
        )
    )
    mutants.append(
        (
            "empty and nonempty partition cardinalities are conflated",
            lambda data: event(data)["partition_effects"][0].__setitem__(
                "inventory_semantics",
                "GENERIC_AFFECTED_MEMBER_SET",
            ),
        )
    )
    mutants.append(
        (
            "member transition reads the wrong key partition",
            lambda data: event(data)["partition_effects"][0]["branches"][0].__setitem__(
                "key_partition",
                "CANONICAL_UNOBSERVED_TO_AUTH_CLOSED_EXACT_MEMBER_SET",
            ),
        )
    )

    def erase_empty_union_discriminant(data: dict[str, Any]) -> None:
        variant = evidence_variant(
            data,
            "TRANSPORT_QUIESCENT_EMPTY_UNIVERSE",
        )
        condition = next(
            item
            for item in variant["truth_conditions"]
            if item["field"] == OBSERVER_GRANT_CLOSURE_AGGREGATION_EVIDENCE_INPUT_FIELD
        )
        condition["value"] = "MEMBER_ADVANCE_BATCH"

    mutants.append(
        ("empty-universe union discriminant erased", erase_empty_union_discriminant)
    )

    def admit_member_bijection_on_empty_input(data: dict[str, Any]) -> None:
        evidence_variant(
            data,
            "TRANSPORT_QUIESCENT_EMPTY_UNIVERSE",
        )["forbidden_fields"].remove(
            OBSERVER_GRANT_CLOSURE_AGGREGATION_MEMBER_EVIDENCE_BIJECTION_FIELD
        )

    mutants.append(
        (
            "empty-universe variant admits a member evidence bijection",
            admit_member_bijection_on_empty_input,
        )
    )

    def widen_empty_proof_consume(data: dict[str, Any]) -> None:
        consume(
            data,
            "ObserverGrantClosureAggregationEmptyUniverseProof",
        ).pop("applies_to_semantic_case_ids")

    mutants.append(
        (
            "empty-universe proof consumed by member-batch cases",
            widen_empty_proof_consume,
        )
    )

    def widen_member_bijection_consume(data: dict[str, Any]) -> None:
        item = consume(
            data,
            "ObserverGrantClosureAggregationMemberEvidenceBijection",
        )
        empty_case_id = next(
            case["semantic_case_id"]
            for case in event(data)["transition_cases"]
            if case["evidence_variant_id"] == "TRANSPORT_QUIESCENT_EMPTY_UNIVERSE"
        )
        item["applies_to_semantic_case_ids"].append(empty_case_id)

    mutants.append(
        (
            "member evidence bijection consumed by the empty-universe case",
            widen_member_bijection_consume,
        )
    )

    def remove_typed_evidence_input_consume(data: dict[str, Any]) -> None:
        target_event = event(data)
        target_event["consumes"] = [
            item
            for item in target_event["consumes"]
            if "ObserverGrantClosureAggregationEvidenceInput" not in item["artifact"]
        ]

    mutants.append(
        (
            "typed aggregation evidence input omitted from consumes",
            remove_typed_evidence_input_consume,
        )
    )
    mutants.append(
        (
            "missing target/output semantic case",
            lambda data: event(data)["transition_cases"].pop(),
        )
    )

    def falsify_output_class(data: dict[str, Any]) -> None:
        variant = event(data)["decision_model"]["evidence_variant_definitions"][0]
        condition = next(
            item
            for item in variant["truth_conditions"]
            if item["field"] == OBSERVER_GRANT_CLOSURE_AGGREGATION_OUTPUT_FIELD
        )
        condition["value"] = (
            "TRANSPORT_QUIESCENT"
            if variant["evidence_variant_id"] != "TRANSPORT_QUIESCENT"
            else "AUTHORIZATION_CLOSED"
        )

    mutants.append(("wrong derived aggregate output class", falsify_output_class))

    def add_local_security_writer(data: dict[str, Any]) -> None:
        contract = event(data)["authority_transaction_contract"]
        contract["write_roles"].append("LOCAL_SECURITY_ENFORCEMENT")
        contract["participant_role_variants"][0]["write_roles"].append(
            "LOCAL_SECURITY_ENFORCEMENT"
        )

    mutants.append(("local-security aggregation writer", add_local_security_writer))
    mutants.append(
        (
            "observer-role marker mutation",
            lambda data: event(data)["common_case_mutates"].append(
                "OBSERVER_ATTACHMENT_TARGET_HISTORY.OBSERVER_ROLE_MARKER"
            ),
        )
    )

    def no_result_case_id(data: dict[str, Any]) -> str:
        return next(
            case["semantic_case_id"]
            for case in event(data)["transition_cases"]
            if case["evidence_variant_id"] == "NO_COMPLETE_AGGREGATE"
        )

    def widen_authorization_receipt(data: dict[str, Any]) -> None:
        sidecar(
            data,
            "ObserverGrantDistributedAuthorizationClosureReceipt",
        )["applies_to_semantic_case_ids"].append(no_result_case_id(data))

    mutants.append(
        (
            "authorization receipt without complete aggregate",
            widen_authorization_receipt,
        )
    )

    def widen_transport_receipt(data: dict[str, Any]) -> None:
        authorization_case = next(
            case["semantic_case_id"]
            for case in event(data)["transition_cases"]
            if case["evidence_variant_id"] == "AUTHORIZATION_CLOSED"
        )
        sidecar(
            data,
            "ObserverGrantTransportQuiescenceReceipt",
        )["applies_to_semantic_case_ids"].append(authorization_case)

    mutants.append(
        ("transport receipt on authorization-only aggregate", widen_transport_receipt)
    )

    def remove_empty_receipt_binding(data: dict[str, Any]) -> None:
        bindings_by_case = sidecar(
            data,
            "ObserverGrantTransportQuiescenceReceipt",
        )["additional_bindings_by_semantic_case"]
        empty_case_id = next(iter(bindings_by_case))
        bindings_by_case[empty_case_id].remove("EXACT_EMPTY_UNIVERSE_PROOF_DIGEST")

    mutants.append(
        (
            "empty transport receipt omits its empty-proof digest",
            remove_empty_receipt_binding,
        )
    )

    def remove_forward_exclusion(data: dict[str, Any]) -> None:
        installed = sidecar(data, "AuthorityTransactionInstalledStateRoot")
        future_binding = next(
            binding
            for binding in installed["forbidden_bindings"]
            if binding.startswith("FUTURE_ARTIFACT::")
        )
        installed["forbidden_bindings"].remove(future_binding)

    mutants.append(
        (
            "post-CAS object can bind a future artifact",
            remove_forward_exclusion,
        )
    )

    def add_spurious_forward_exclusion(data: dict[str, Any]) -> None:
        sidecar(
            data,
            "CrossStoreProtectedOutputDeliveryCapsule",
        )["forbidden_bindings"].append(
            "FUTURE_ARTIFACT::unknown-type::UnknownFutureArtifact"
        )

    mutants.append(
        (
            "post-CAS forward exclusion set is not exact",
            add_spurious_forward_exclusion,
        )
    )
    mutants.append(
        (
            "post-CAS DAG admits a redundant dependency",
            lambda data: sidecar(
                data,
                "ObserverAttachmentTargetHistoryCommitReceipt",
            )[
                "depends_on"
            ].append(
                "authority-transaction-installed-state-root-type::"
                "AuthorityTransactionInstalledStateRoot"
            ),
        )
    )

    def widen_result_envelope(data: dict[str, Any]) -> None:
        sidecar(
            data,
            "ProtectedObserverGrantClosureResultEnvelope",
        )["applies_to_semantic_case_ids"].append(no_result_case_id(data))

    mutants.append(
        ("result envelope without complete aggregate", widen_result_envelope)
    )

    def remove_stronger_only_binding(data: dict[str, Any]) -> None:
        sidecar(
            data,
            "ProtectedObserverGrantClosureResultEnvelope",
        )["additional_bindings"].remove(
            "TRANSPORT_QUIESCENT_EXCLUDES_SIBLING_AUTHORIZATION_CLOSED_ENVELOPE"
        )

    mutants.append(
        ("sibling authorization envelope escape", remove_stronger_only_binding)
    )
    mutants.append(
        (
            "missing receipt-free aggregation candidate",
            lambda data: event(data)["creates"].__setitem__(
                slice(None),
                [
                    item
                    for item in event(data)["creates"]
                    if "ObserverGrantClosureAggregationCandidate"
                    not in item["artifact"]
                ],
            ),
        )
    )
    mutants.append(
        (
            "unexpected authority-bearing aggregation output",
            lambda data: event(data)["creates"].append(
                {
                    "artifact": ("authority-policy-result-type::AuthorityPolicyResult"),
                    "role": "ALLOW_POLICY_RESULT",
                }
            ),
        )
    )

    def remove_lattice_evidence_binding(data: dict[str, Any]) -> None:
        event(data)["pre_cas_content"]["required_bindings"].remove(
            "UNKNOWN_TO_TRANSPORT_QUIESCENT_AND_EVIDENCE_DOWNGRADE_ARE_FORBIDDEN"
        )

    mutants.append(
        (
            "missing monotone-lattice evidence binding",
            remove_lattice_evidence_binding,
        )
    )
    mutants.append(
        (
            "caller operation ID required by the aggregation fact",
            lambda data: event(data)["pre_cas_content"]["required_bindings"].append(
                "OPERATION_ID"
            ),
        )
    )
    mutants.append(
        (
            "caller operation ID no longer forbidden",
            lambda data: event(data)["pre_cas_content"]["forbidden_bindings"].remove(
                "CALLER_SUPPLIED_OPERATION_ID"
            ),
        )
    )
    mutants.append(
        (
            "semantic input digest binding omitted",
            lambda data: event(data)["pre_cas_content"]["required_bindings"].remove(
                "EXACT_PRE_CAS_SEMANTIC_INPUT_DIGEST_EXCLUDING_OPERATION_KEY_"
                "CANDIDATES_RECEIPTS_AND_SIDECARS"
            ),
        )
    )

    def grant_authority(data: dict[str, Any]) -> None:
        variant = event(data)["decision_model"]["evidence_variant_definitions"][0]
        condition = next(
            item
            for item in variant["truth_conditions"]
            if item["field"]
            == OBSERVER_GRANT_CLOSURE_AGGREGATION_AUTHORITY_EFFECT_FIELD
        )
        condition["value"] = "ALLOW"

    mutants.append(("aggregation grants authority", grant_authority))

    killed = 0
    for label, mutate in mutants:
        hostile = copy.deepcopy(baseline)
        mutate(hostile)
        try:
            _validate_observer_grant_closure_aggregation_contract(hostile)
        except ClosureCheckError:
            killed += 1
        else:
            fail(f"closure-aggregation self-test accepted {label}")
    return killed


def _run_request_successor_contract_self_test() -> int:
    edge_catalog: list[dict[str, str]] = []
    edge_id_by_key: dict[tuple[str, str, str], str] = {}

    def edge_id(domain: str, source: str, target: str) -> str:
        key = (domain, source, target)
        if key not in edge_id_by_key:
            identifier = f"E{len(edge_catalog) + 1:04d}"
            edge_id_by_key[key] = identifier
            edge_catalog.append(
                {
                    "edge_id": identifier,
                    "from_state": source,
                    "state_domain": domain,
                    "to_state": target,
                }
            )
        return edge_id_by_key[key]

    def transition_case(
        *,
        case_id: str,
        variant_id: str,
        outer_pair: tuple[str, str],
        local_pair: tuple[str, str],
        operation_pair: tuple[str, str],
        deadline_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "case_contract": {
                "deadline_condition_ids": deadline_ids or [],
            },
            "evidence_variant_id": variant_id,
            "semantic_case_id": case_id,
            "state_edge_refs": [
                edge_id("OUTER_LIFECYCLE", *outer_pair),
                edge_id("LOCAL_GRANT_STATE", *local_pair),
                edge_id(
                    "OBSERVER_GRANT_REQUEST_OPERATION_STATE",
                    *operation_pair,
                ),
            ],
        }

    def decision_model(
        exact_values_by_variant: dict[str, dict[str, str]],
    ) -> dict[str, Any]:
        return {
            "evidence_variant_definitions": [
                {
                    "evidence_variant_id": variant_id,
                    "forbidden_fields": [],
                    "required_fields": sorted(exact_values),
                    "truth_conditions": [
                        {
                            "field": field,
                            "operator": "EQUALS",
                            "value": value,
                        }
                        for field, value in sorted(exact_values.items())
                    ],
                }
                for variant_id, exact_values in sorted(exact_values_by_variant.items())
            ]
        }

    events: list[dict[str, Any]] = []
    prepare_cases = []
    prepare_exact_values = {}
    prepare_local_pair_by_kind = {
        "ATTACH": ("PENDING_FIRST_ATTACH", "PENDING_FIRST_ATTACH"),
        "REATTACH": ("TERMINAL", "TERMINAL"),
        "RENEW": ("LIVE", "LIVE"),
    }
    for kind, local_pair in prepare_local_pair_by_kind.items():
        variant_id = f"{kind}_PREPARE"
        prepare_exact_values[variant_id] = {OBSERVER_GRANT_REQUEST_KIND_FIELD: kind}
        prepare_cases.append(
            transition_case(
                case_id=f"PREPARE_{kind}",
                variant_id=variant_id,
                outer_pair=("OPEN_ADMISSION", "OPEN_ADMISSION"),
                local_pair=local_pair,
                operation_pair=("ABSENT", "INTENT_PREPARED"),
            )
        )
    events.append(
        {
            "deadline_conditions": {"conditions": []},
            "decision_model": decision_model(prepare_exact_values),
            "event_id": OBSERVER_GRANT_REQUEST_PREPARE_EVENT,
            "transition_cases": prepare_cases,
        }
    )

    begin_contract_by_event = {
        "BEGIN_OBSERVER_GRANT_ATTACH_REQUEST": (
            "PENDING_FIRST_ATTACH",
            "PENDING_FIRST_ATTACH",
        ),
        "BEGIN_OBSERVER_GRANT_REATTACH_REQUEST": (
            "TERMINAL",
            "TERMINAL",
        ),
        "BEGIN_OBSERVER_GRANT_RENEWAL_REQUEST": (
            "LIVE",
            "LIVE_RENEW_PENDING",
        ),
    }
    for event_id, local_pair in begin_contract_by_event.items():
        events.append(
            {
                "deadline_conditions": {"conditions": []},
                "event_id": event_id,
                "transition_cases": [
                    transition_case(
                        case_id=event_id,
                        variant_id="TYPED_EVENT_FACT_VALIDATED",
                        outer_pair=(
                            "OPEN_ADMISSION",
                            "OPEN_ADMISSION",
                        ),
                        local_pair=local_pair,
                        operation_pair=(
                            "INTENT_PREPARED",
                            "PENDING_RESPONSE",
                        ),
                    )
                ],
            }
        )

    ambiguity_cases = []
    ambiguity_exact_values = {}
    for kind in sorted(OBSERVER_GRANT_REQUEST_KINDS):
        variant_id = f"{kind}_AMBIGUOUS"
        ambiguity_exact_values[variant_id] = {OBSERVER_GRANT_REQUEST_KIND_FIELD: kind}
        for outer_phase in sorted(OBSERVER_GRANT_REQUEST_RESOLUTION_OUTER_PHASES):
            local_pair = (
                {
                    "ATTACH": (
                        "PENDING_FIRST_ATTACH",
                        "PENDING_FIRST_ATTACH",
                    ),
                    "REATTACH": ("TERMINAL", "TERMINAL"),
                    "RENEW": (
                        "LIVE_RENEW_PENDING",
                        "LIVE_RENEW_PENDING",
                    ),
                }[kind]
                if outer_phase == "OPEN_ADMISSION"
                else {
                    "ATTACH": ("PENDING_FIRST_ATTACH", "TERMINAL"),
                    "REATTACH": ("TERMINAL", "TERMINAL"),
                    "RENEW": (
                        "LIVE_RENEW_PENDING",
                        "RENEW_PENDING_PREDECESSOR_CLOSED",
                    ),
                }[kind]
            )
            ambiguity_cases.append(
                transition_case(
                    case_id=f"AMBIGUOUS_{kind}_{outer_phase}",
                    variant_id=variant_id,
                    outer_pair=(outer_phase, outer_phase),
                    local_pair=local_pair,
                    operation_pair=(
                        "PENDING_RESPONSE",
                        "AMBIGUOUS_SERVER_ACCEPTANCE",
                    ),
                )
            )
    events.append(
        {
            "deadline_conditions": {"conditions": []},
            "decision_model": decision_model(ambiguity_exact_values),
            "event_id": OBSERVER_GRANT_REQUEST_AMBIGUITY_EVENT,
            "transition_cases": ambiguity_cases,
        }
    )

    intent_resolution_cases = []
    intent_resolution_exact_values = {}
    for kind in sorted(OBSERVER_GRANT_REQUEST_KINDS):
        for cause in (
            "SERVER_SLOT_CANCELED_UNUSED",
            "SERVER_SLOT_EXPIRED_UNUSED",
        ):
            variant_id = f"{kind}_{cause}"
            intent_resolution_exact_values[variant_id] = {
                OBSERVER_GRANT_REQUEST_INTENT_CAUSE_FIELD: cause,
                OBSERVER_GRANT_REQUEST_KIND_FIELD: kind,
            }
            for outer_phase in sorted(OBSERVER_GRANT_REQUEST_RESOLUTION_OUTER_PHASES):
                is_open = outer_phase == "OPEN_ADMISSION"
                local_pairs = {
                    "ATTACH": {
                        (
                            "PENDING_FIRST_ATTACH",
                            "PENDING_FIRST_ATTACH" if is_open else "TERMINAL",
                        ),
                        ("TERMINAL", "TERMINAL"),
                    },
                    "REATTACH": {("TERMINAL", "TERMINAL")},
                    "RENEW": {
                        ("LIVE", "LIVE" if is_open else "DETACH_PENDING"),
                        ("DETACH_PENDING", "DETACH_PENDING"),
                        ("TERMINAL", "TERMINAL"),
                    },
                }[kind]
                for local_pair in sorted(local_pairs):
                    intent_resolution_cases.append(
                        transition_case(
                            case_id=(
                                f"INTENT_RESOLVE_{kind}_{cause}_{outer_phase}_"
                                f"{local_pair[0]}_{local_pair[1]}"
                            ),
                            variant_id=variant_id,
                            outer_pair=(outer_phase, outer_phase),
                            local_pair=local_pair,
                            operation_pair=(
                                "INTENT_PREPARED",
                                "RESOLVED_WITHOUT_INSTALLATION",
                            ),
                        )
                    )
    events.append(
        {
            "deadline_conditions": {"conditions": []},
            "decision_model": decision_model(intent_resolution_exact_values),
            "event_id": (OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT),
            "transition_cases": intent_resolution_cases,
        }
    )

    observation_operation_pairs = {
        (
            "AMBIGUOUS_SERVER_ACCEPTANCE",
            "TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE",
        ),
        (
            "PENDING_RESPONSE",
            "TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE",
        ),
        (
            "TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE",
            "TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE",
        ),
    }
    observation_cases = []
    observation_exact_values = {}
    for kind in sorted(OBSERVER_GRANT_REQUEST_KINDS):
        variant_id = f"{kind}_PROTECTED_TERMINAL_RESULT_OBSERVED"
        observation_exact_values[variant_id] = {OBSERVER_GRANT_REQUEST_KIND_FIELD: kind}
        for outer_phase in sorted(OBSERVER_GRANT_REQUEST_RESOLUTION_OUTER_PHASES):
            for operation_pair in sorted(observation_operation_pairs):
                local_pair = {
                    "ATTACH": (
                        ("TERMINAL", "TERMINAL")
                        if operation_pair[0]
                        == "TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE"
                        else ("PENDING_FIRST_ATTACH", "TERMINAL")
                    ),
                    "REATTACH": ("TERMINAL", "TERMINAL"),
                    "RENEW": (
                        (
                            "RENEW_PENDING_PREDECESSOR_CLOSED",
                            "RENEW_PENDING_PREDECESSOR_CLOSED",
                        )
                        if operation_pair[0]
                        == "TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE"
                        else (
                            "LIVE_RENEW_PENDING",
                            "RENEW_PENDING_PREDECESSOR_CLOSED",
                        )
                    ),
                }[kind]
                observation_cases.append(
                    transition_case(
                        case_id=(f"OBSERVE_{kind}_{outer_phase}_{operation_pair[0]}"),
                        variant_id=variant_id,
                        outer_pair=(outer_phase, outer_phase),
                        local_pair=local_pair,
                        operation_pair=operation_pair,
                    )
                )
    events.append(
        {
            "deadline_conditions": {"conditions": []},
            "decision_model": decision_model(observation_exact_values),
            "event_id": (OBSERVER_GRANT_REQUEST_TERMINAL_OBSERVATION_EVENT),
            "transition_cases": observation_cases,
        }
    )

    install_local_pairs = {
        "INSTALL_OBSERVER_GRANT_FROM_ACCEPTED_RESPONSE": {
            ("PENDING_FIRST_ATTACH", "LIVE")
        },
        "INSTALL_OBSERVER_GRANT_REATTACHMENT_FROM_ACCEPTED_RESPONSE": {
            ("TERMINAL", "LIVE")
        },
        "INSTALL_OBSERVER_GRANT_RENEWAL_FROM_ACCEPTED_RESPONSE": {
            ("LIVE_RENEW_PENDING", "LIVE"),
            ("RENEW_PENDING_PREDECESSOR_CLOSED", "LIVE"),
        },
    }
    for event_id, local_pairs in install_local_pairs.items():
        events.append(
            {
                "deadline_conditions": {"conditions": []},
                "event_id": event_id,
                "transition_cases": [
                    transition_case(
                        case_id=f"{event_id}_{index}",
                        variant_id="PROTECTED_LIVE_RESPONSE_VERIFIED",
                        outer_pair=(
                            "OPEN_ADMISSION",
                            "OPEN_ADMISSION",
                        ),
                        local_pair=local_pair,
                        operation_pair=(
                            "PENDING_RESPONSE",
                            "INSTALLED",
                        ),
                    )
                    for index, local_pair in enumerate(sorted(local_pairs))
                ],
            }
        )

    resolver_kind_by_event = {
        "RESOLVE_OBSERVER_GRANT_ATTACH_REQUEST_WITHOUT_INSTALLATION": ("ATTACH"),
        "RESOLVE_OBSERVER_GRANT_REATTACH_REQUEST_WITHOUT_INSTALLATION": ("REATTACH"),
        "RESOLVE_OBSERVER_GRANT_RENEWAL_WITHOUT_INSTALLATION": "RENEW",
    }
    accepted_cause = "ACCEPTED_GRANT_FULLY_CLOSED_WITHOUT_LOCAL_INSTALLATION"
    unused_causes = {
        "SERVER_SLOT_CANCELED_UNUSED",
        "SERVER_SLOT_EXPIRED_UNUSED",
    }
    open_local_pairs: dict[tuple[str, str], set[tuple[str, str]]] = {
        ("ATTACH", accepted_cause): {("TERMINAL", "TERMINAL")},
        ("REATTACH", accepted_cause): {("TERMINAL", "TERMINAL")},
        ("RENEW", accepted_cause): {
            (
                "RENEW_PENDING_PREDECESSOR_CLOSED",
                "TERMINAL",
            ),
            ("TERMINAL", "TERMINAL"),
        },
    }
    deny_local_pairs = {
        ("ATTACH", accepted_cause): {("TERMINAL", "TERMINAL")},
        ("REATTACH", accepted_cause): {("TERMINAL", "TERMINAL")},
        ("RENEW", accepted_cause): {
            ("RENEW_PENDING_PREDECESSOR_CLOSED", "TERMINAL"),
            ("TERMINAL", "TERMINAL"),
        },
    }
    for cause in unused_causes:
        open_local_pairs[("ATTACH", cause)] = {
            ("PENDING_FIRST_ATTACH", "PENDING_FIRST_ATTACH"),
            ("TERMINAL", "TERMINAL"),
        }
        open_local_pairs[("REATTACH", cause)] = {("TERMINAL", "TERMINAL")}
        open_local_pairs[("RENEW", cause)] = {
            ("DETACH_PENDING", "DETACH_PENDING"),
            ("LIVE_RENEW_PENDING", "LIVE"),
            ("LIVE_RENEW_PENDING", "TERMINAL"),
            (
                "RENEW_PENDING_PREDECESSOR_CLOSED",
                "TERMINAL",
            ),
            ("TERMINAL", "TERMINAL"),
        }
        deny_local_pairs[("ATTACH", cause)] = {
            ("PENDING_FIRST_ATTACH", "TERMINAL"),
            ("TERMINAL", "TERMINAL"),
        }
        deny_local_pairs[("REATTACH", cause)] = {("TERMINAL", "TERMINAL")}
        deny_local_pairs[("RENEW", cause)] = {
            ("DETACH_PENDING", "DETACH_PENDING"),
            ("LIVE_RENEW_PENDING", "DETACH_PENDING"),
            ("RENEW_PENDING_PREDECESSOR_CLOSED", "TERMINAL"),
            ("TERMINAL", "TERMINAL"),
        }

    for event_id, kind in resolver_kind_by_event.items():
        cases = []
        for cause in sorted(OBSERVER_GRANT_REQUEST_TERMINAL_RESOLUTION_CAUSES):
            operation_sources = (
                {"TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE"}
                if cause == accepted_cause
                else {
                    "AMBIGUOUS_SERVER_ACCEPTANCE",
                    "PENDING_RESPONSE",
                }
            )
            for outer_phase in sorted(OBSERVER_GRANT_REQUEST_RESOLUTION_OUTER_PHASES):
                local_pairs = (
                    open_local_pairs[(kind, cause)]
                    if outer_phase == "OPEN_ADMISSION"
                    else deny_local_pairs[(kind, cause)]
                )
                for operation_source in sorted(operation_sources):
                    for local_pair in sorted(local_pairs):
                        deadline_ids = (
                            ["DPRE"]
                            if kind == "RENEW" and local_pair[1] == "LIVE"
                            else []
                        )
                        cases.append(
                            transition_case(
                                case_id=(
                                    f"{event_id}_{cause}_{outer_phase}_"
                                    f"{operation_source}_{local_pair[0]}_"
                                    f"{local_pair[1]}_{len(cases)}"
                                ),
                                variant_id=cause,
                                outer_pair=(outer_phase, outer_phase),
                                local_pair=local_pair,
                                operation_pair=(
                                    operation_source,
                                    "RESOLVED_WITHOUT_INSTALLATION",
                                ),
                                deadline_ids=deadline_ids,
                            )
                        )
        events.append(
            {
                "deadline_conditions": {
                    "conditions": (
                        [
                            {
                                "comparison": "STRICTLY_BEFORE",
                                "condition_id": "DPRE",
                                "deadline_kind": (
                                    "OBSERVER_RENEWAL_PREDECESSOR_ADMISSION_NOT_AFTER"
                                ),
                            }
                        ]
                        if kind == "RENEW"
                        else []
                    )
                },
                "decision_model": decision_model(
                    {
                        cause: {OBSERVER_GRANT_REQUEST_CAUSE_FIELD: cause}
                        for cause in (OBSERVER_GRANT_REQUEST_TERMINAL_RESOLUTION_CAUSES)
                    }
                ),
                "event_id": event_id,
                "transition_cases": cases,
            }
        )

    selector = {
        "events": events,
        "state_domains": [
            {"state_domain": domain_id}
            for domain_id in OBSERVER_GRANT_REQUEST_SPLIT_PRODUCT_DOMAINS
        ],
        "state_edge_catalog": edge_catalog,
    }
    require(
        not _observer_grant_request_successor_contract_issues(selector),
        "request-successor self-test rejected the closed successor product",
    )
    require(
        not _observer_grant_request_causal_transition_contract_issues(selector),
        "request-successor fixture rejected the exact operation lifecycle",
    )

    wrong_prepare_phase = copy.deepcopy(selector)
    prepare_event = next(
        event
        for event in wrong_prepare_phase["events"]
        if event["event_id"] == OBSERVER_GRANT_REQUEST_PREPARE_EVENT
    )
    prepare_case = prepare_event["transition_cases"][0]
    wrong_edge_lookup = {
        edge["edge_id"]: edge for edge in wrong_prepare_phase["state_edge_catalog"]
    }
    prepare_case["state_edge_refs"] = [
        (
            edge_id_by_key[
                (
                    "OBSERVER_GRANT_REQUEST_OPERATION_STATE",
                    "INTENT_PREPARED",
                    "PENDING_RESPONSE",
                )
            ]
            if wrong_edge_lookup[edge_ref]["state_domain"]
            == "OBSERVER_GRANT_REQUEST_OPERATION_STATE"
            else edge_ref
        )
        for edge_ref in prepare_case["state_edge_refs"]
    ]
    require(
        _observer_grant_request_causal_transition_contract_issues(wrong_prepare_phase),
        "request-successor self-test accepted PREPARE skipping intent phase",
    )

    kind_erased_prepare = copy.deepcopy(selector)
    prepare_event = next(
        event
        for event in kind_erased_prepare["events"]
        if event["event_id"] == OBSERVER_GRANT_REQUEST_PREPARE_EVENT
    )
    prepare_event["decision_model"]["evidence_variant_definitions"][0][
        "truth_conditions"
    ] = []
    require(
        _observer_grant_request_successor_contract_issues(kind_erased_prepare),
        "request-successor self-test accepted a kind-erased PREPARE case",
    )

    accepted_prepared_intent = copy.deepcopy(selector)
    intent_event = next(
        event
        for event in accepted_prepared_intent["events"]
        if event["event_id"] == OBSERVER_GRANT_REQUEST_INTENT_RESOLUTION_EVENT
    )
    cause_condition = next(
        condition
        for condition in intent_event["decision_model"]["evidence_variant_definitions"][
            0
        ]["truth_conditions"]
        if condition["field"] == OBSERVER_GRANT_REQUEST_INTENT_CAUSE_FIELD
    )
    cause_condition["value"] = "ACCEPTED_GRANT_FULLY_CLOSED_WITHOUT_LOCAL_INSTALLATION"
    require(
        _observer_grant_request_successor_contract_issues(accepted_prepared_intent),
        ("request-successor self-test accepted an accepted-grant cause before BEGIN"),
    )

    accepted_restores_live = copy.deepcopy(selector)
    renewal_resolver = next(
        event
        for event in accepted_restores_live["events"]
        if event["event_id"] == "RESOLVE_OBSERVER_GRANT_RENEWAL_WITHOUT_INSTALLATION"
    )
    hostile_case = next(
        case
        for case in renewal_resolver["transition_cases"]
        if case["evidence_variant_id"] == accepted_cause
    )
    hostile_edge_lookup = {
        edge["edge_id"]: edge for edge in accepted_restores_live["state_edge_catalog"]
    }
    hostile_case["state_edge_refs"] = [
        (
            edge_id_by_key[
                (
                    "LOCAL_GRANT_STATE",
                    "RENEW_PENDING_PREDECESSOR_CLOSED",
                    "LIVE",
                )
            ]
            if hostile_edge_lookup[edge_ref]["state_domain"] == "LOCAL_GRANT_STATE"
            else edge_ref
        )
        for edge_ref in hostile_case["state_edge_refs"]
    ]
    require(
        _observer_grant_request_successor_contract_issues(accepted_restores_live),
        "request-successor self-test accepted closed G1 restoring G0",
    )

    missing_deny_phase = copy.deepcopy(selector)
    attach_resolver = next(
        event
        for event in missing_deny_phase["events"]
        if event["event_id"]
        == "RESOLVE_OBSERVER_GRANT_ATTACH_REQUEST_WITHOUT_INSTALLATION"
    )
    edge_lookup = {
        edge["edge_id"]: edge for edge in missing_deny_phase["state_edge_catalog"]
    }
    attach_resolver["transition_cases"] = [
        case
        for case in attach_resolver["transition_cases"]
        if not (
            case["evidence_variant_id"] == "SERVER_SLOT_CANCELED_UNUSED"
            and any(
                edge_lookup[edge_ref]["state_domain"] == "OUTER_LIFECYCLE"
                and edge_lookup[edge_ref]["from_state"]
                == "EMERGENCY_FENCED_CLOSURE_PENDING"
                for edge_ref in case["state_edge_refs"]
            )
        )
    ]
    require(
        _observer_grant_request_successor_contract_issues(missing_deny_phase),
        "request-successor self-test accepted missing deny-phase closure",
    )

    missing_restore_deadline = copy.deepcopy(selector)
    renewal_resolver = next(
        event
        for event in missing_restore_deadline["events"]
        if event["event_id"] == "RESOLVE_OBSERVER_GRANT_RENEWAL_WITHOUT_INSTALLATION"
    )
    edge_lookup = {
        edge["edge_id"]: edge for edge in missing_restore_deadline["state_edge_catalog"]
    }
    live_restore_case = next(
        case
        for case in renewal_resolver["transition_cases"]
        if case["evidence_variant_id"] == "SERVER_SLOT_CANCELED_UNUSED"
        and any(
            edge_lookup[edge_ref]["state_domain"] == "LOCAL_GRANT_STATE"
            and edge_lookup[edge_ref]["to_state"] == "LIVE"
            for edge_ref in case["state_edge_refs"]
        )
    )
    live_restore_case["case_contract"]["deadline_condition_ids"] = []
    require(
        _observer_grant_request_successor_contract_issues(missing_restore_deadline),
        "request-successor self-test accepted deadline-free G0 restore",
    )
    return 6


def _run_request_domain_contract_self_test() -> int:
    selector = {
        "state_domains": [
            {
                "initial_state": contract["initial_state"],
                **(
                    {
                        "root_terminal_safe_states": sorted(
                            contract["root_terminal_safe_states"]
                        )
                    }
                    if "root_terminal_safe_states" in contract
                    else {}
                ),
                "state_domain": domain_id,
                "states": sorted(contract["states"]),
                "terminality": contract["terminality"],
                "terminal_states": sorted(contract["terminal_states"]),
            }
            for domain_id, contract in (
                OBSERVER_GRANT_REQUEST_SPLIT_DOMAIN_CONTRACT.items()
            )
        ]
    }
    require(
        not _observer_grant_request_domain_contract_issues(selector),
        "request-domain self-test rejected the exact split unions",
    )

    extra_state = copy.deepcopy(selector)
    extra_state["state_domains"][0]["states"].append("UNKNOWN_PERMISSIVE")
    require(
        _observer_grant_request_domain_contract_issues(extra_state),
        "request-domain self-test accepted an open state union",
    )

    wrong_initial = copy.deepcopy(selector)
    wrong_initial["state_domains"][1]["initial_state"] = "LIVE"
    require(
        _observer_grant_request_domain_contract_issues(wrong_initial),
        "request-domain self-test accepted an optimistic initial state",
    )

    legacy_root = copy.deepcopy(selector)
    legacy_root["state_domains"].append(
        {
            "initial_state": "UNINITIALIZED",
            "state_domain": "ROOT",
            "states": ["UNINITIALIZED"],
            "terminality": "ALL_REACH_TERMINAL",
            "terminal_states": [],
        }
    )
    require(
        _observer_grant_request_domain_contract_issues(legacy_root),
        "request-domain self-test accepted the legacy conflated root",
    )
    return 3


def _require_selector_root_domain_contract(
    *,
    selector_id: str,
    domain_ids: list[str],
    allow_known_incomplete: bool,
) -> None:
    """Permit the observer split root without weakening every other selector."""

    root_count = domain_ids.count("ROOT")
    if selector_id != "OBSERVER_ADMISSION":
        require_exact(
            root_count,
            1,
            f"{selector_id}: ROOT domain count",
        )
        return

    split_domains = {
        "OUTER_LIFECYCLE",
        "LOCAL_GRANT_STATE",
    }
    present_split_domains = split_domains & set(domain_ids)
    require(
        present_split_domains in (set(), split_domains),
        (
            "OBSERVER_ADMISSION: partial split root domains "
            f"{sorted(present_split_domains)}"
        ),
    )
    if present_split_domains == split_domains:
        require_exact(
            root_count,
            0,
            "OBSERVER_ADMISSION: legacy ROOT domain count after split",
        )
        return
    require(
        allow_known_incomplete,
        "OBSERVER_ADMISSION: split root domains are required",
    )
    require_exact(
        root_count,
        1,
        "OBSERVER_ADMISSION: legacy ROOT diagnostic domain count",
    )


def _run_selector_root_domain_contract_self_test() -> int:
    _require_selector_root_domain_contract(
        selector_id="OBSERVER_ADMISSION",
        domain_ids=["LOCAL_GRANT_STATE", "OUTER_LIFECYCLE"],
        allow_known_incomplete=False,
    )
    _require_selector_root_domain_contract(
        selector_id="OBSERVER_ADMISSION",
        domain_ids=["ROOT"],
        allow_known_incomplete=True,
    )
    hostile_cases = (
        (
            "OBSERVER_ADMISSION",
            ["LOCAL_GRANT_STATE", "OUTER_LIFECYCLE", "ROOT"],
            False,
            "observer split retained legacy ROOT",
        ),
        (
            "OBSERVER_ADMISSION",
            ["LOCAL_GRANT_STATE", "ROOT"],
            True,
            "observer partial split",
        ),
        (
            "OBSERVER_ADMISSION",
            ["ROOT"],
            False,
            "observer legacy ROOT outside diagnostic mode",
        ),
        (
            "SECURITY_AUTHORITY",
            ["SECURITY_STATE"],
            False,
            "non-observer selector without ROOT",
        ),
    )
    for selector_id, domain_ids, allow_known_incomplete, label in hostile_cases:
        try:
            _require_selector_root_domain_contract(
                selector_id=selector_id,
                domain_ids=domain_ids,
                allow_known_incomplete=allow_known_incomplete,
            )
        except ClosureCheckError:
            pass
        else:
            fail(f"selector-root self-test accepted {label}")
    return len(hostile_cases)


def _validate_selector_structure(
    data: dict[str, Any],
    artifacts: set[str],
    *,
    allow_known_incomplete: bool = False,
) -> tuple[int, int, int, int, int]:
    selectors = data["selectors"]
    require(isinstance(selectors, list), "selectors must be an array")
    ids = [selector["selector_id"] for selector in selectors]
    require_exact(ids, sorted(ids), "selector order")
    require_unique(ids, "selector IDs")
    require_exact(set(ids), EXPECTED_SELECTORS, "selector set")

    domain_count = 0
    event_count = 0
    case_count = 0
    partition_branch_count = 0
    sidecar_count = 0

    for selector in selectors:
        selector_id = selector["selector_id"]
        require(
            SEMANTIC_ID.fullmatch(selector_id) is not None,
            f"{selector_id}: invalid selector ID",
        )
        require_exact(
            selector["unknown_default_legacy_behavior"],
            "REJECT",
            f"{selector_id}: unknown/default behavior",
        )
        for field in ("selector", "root", "generic_receipt"):
            _validate_artifact_ref(
                selector[field],
                artifacts,
                f"{selector_id}.{field}",
            )

        domains = selector["state_domains"]
        domain_ids = [item["state_domain"] for item in domains]
        require_unique(domain_ids, f"{selector_id}: state domains")
        _require_selector_root_domain_contract(
            selector_id=selector_id,
            domain_ids=domain_ids,
            allow_known_incomplete=allow_known_incomplete,
        )
        domain_by_id = {item["state_domain"]: item for item in domains}
        transitions_by_domain: dict[str, set[tuple[str, str]]] = {
            domain_id: set() for domain_id in domain_by_id
        }
        domain_count += len(domains)
        for state_domain in domains:
            domain_id = state_domain["state_domain"]
            states = state_domain["states"]
            require_unique(states, f"{selector_id}.{domain_id}: states")
            require_exact(
                states,
                sorted(states),
                f"{selector_id}.{domain_id}: state order",
            )
            require(
                state_domain["initial_state"] in states,
                f"{selector_id}.{domain_id}: initial state is not declared",
            )
            require(
                set(state_domain["terminal_states"]).issubset(states),
                f"{selector_id}.{domain_id}: unknown terminal state",
            )
            require(
                state_domain["terminality"] in TERMINALITY_POLICIES,
                (
                    f"{selector_id}.{domain_id}: unknown terminality "
                    f"policy {state_domain['terminality']!r}"
                ),
            )
            if state_domain["terminality"] == "ALL_REACH_TERMINAL":
                require(
                    bool(state_domain["terminal_states"]),
                    (
                        f"{selector_id}.{domain_id}: "
                        "ALL_REACH_TERMINAL has no terminal states"
                    ),
                )
            if not state_domain["terminal_states"]:
                require(
                    state_domain["terminality"] in NONTERMINAL_DOMAIN_POLICIES,
                    (
                        f"{selector_id}.{domain_id}: empty terminal-state set "
                        "is not authorized by terminality policy"
                    ),
                )
            require_unique(
                state_domain["key_coordinates"],
                f"{selector_id}.{domain_id}: key coordinates",
            )
            require_unique(
                state_domain["join_fields"],
                f"{selector_id}.{domain_id}: join fields",
            )
            require(
                set(state_domain["key_coordinates"]).issubset(
                    state_domain["join_fields"]
                ),
                f"{selector_id}.{domain_id}: key coordinates not in joins",
            )
            _validate_artifact_ref(
                state_domain["key_type"],
                artifacts,
                f"{selector_id}.{domain_id}.key_type",
            )
            require_exact(
                state_domain["owner_selector_id"],
                selector_id,
                f"{selector_id}.{domain_id}: owner",
            )

        edge_catalog = selector["state_edge_catalog"]
        edge_ids = [item["edge_id"] for item in edge_catalog]
        require_unique(edge_ids, f"{selector_id}: state edge IDs")
        require(
            all(EDGE_ID.fullmatch(value) for value in edge_ids),
            f"{selector_id}: invalid state edge ID",
        )
        edge_by_id = {item["edge_id"]: item for item in edge_catalog}
        referenced_edge_ids: set[str] = set()
        for state_edge in edge_catalog:
            domain_id = state_edge["state_domain"]
            require(
                domain_id in domain_by_id,
                f"{selector_id}.{state_edge['edge_id']}: unknown domain",
            )
            state_domain = domain_by_id[domain_id]
            require(
                state_edge["from_state"] in state_domain["states"],
                f"{selector_id}.{state_edge['edge_id']}: unknown source state",
            )
            require(
                state_edge["to_state"] in state_domain["states"],
                f"{selector_id}.{state_edge['edge_id']}: unknown target state",
            )
            require_exact(
                state_edge["key_ref"],
                state_domain["key_type"],
                f"{selector_id}.{state_edge['edge_id']}: key type",
            )
            require_exact(
                state_edge["preserve_siblings"],
                True,
                f"{selector_id}.{state_edge['edge_id']}: sibling preservation",
            )
            transitions_by_domain[domain_id].add(
                (state_edge["from_state"], state_edge["to_state"])
            )

        events = selector["events"]
        event_ids = [event["event_id"] for event in events]
        require_exact(
            event_ids,
            sorted(event_ids),
            f"{selector_id}: event order",
        )
        require_unique(event_ids, f"{selector_id}: event IDs")
        event_count += len(events)
        for event in events:
            event_id = event["event_id"]
            label = f"{selector_id}.{event_id}"
            require(
                SEMANTIC_ID.fullmatch(event_id) is not None,
                f"{label}: invalid event ID",
            )
            _validate_artifact_ref(
                event["transition_kind"],
                artifacts,
                f"{label}.transition_kind",
            )
            expected_transition_kind = (
                SHARED_TRANSITION_KIND_BY_EVENT.get(event_id, event_id)
                if selector_id == "OBSERVER_AUTHORIZATION"
                else event_id
            )
            require_exact(
                event["transition_kind"].split("::", 1)[1],
                expected_transition_kind,
                f"{label}: transition-kind allocation",
            )
            require(
                event["transition_kind_state_domain"] in domain_by_id,
                f"{label}: transition kind has an unknown state domain",
            )
            _validate_artifact_ref(
                event["pre_cas_content"]["artifact"],
                artifacts,
                f"{label}.pre_cas_content",
            )
            require_unique(
                event["pre_cas_content"]["required_bindings"],
                f"{label}: required bindings",
            )
            for reference in event["subordinate_transition_kinds"]:
                _validate_artifact_ref(
                    reference,
                    artifacts,
                    f"{label}.subordinate_transition_kind",
                )
            require(
                event["operation_scope"]
                in {"ROOT_ONLY", "EXACT_ONE_KEY", "BOUNDED_KEY_SET"},
                f"{label}: invalid operation scope",
            )

            partitions = event["partition_effects"]
            partition_ids = [item["partition_id"] for item in partitions]
            require_unique(partition_ids, f"{label}: partition IDs")
            require(
                all(PARTITION_ID.fullmatch(value) for value in partition_ids),
                f"{label}: invalid partition ID",
            )
            partition_by_id = {item["partition_id"]: item for item in partitions}

            cases = event["transition_cases"]
            semantic_case_ids = [item["semantic_case_id"] for item in cases]
            require(cases, f"{label}: no semantic cases")
            require_unique(semantic_case_ids, f"{label}: semantic cases")
            decision_model = event["decision_model"]
            require_exact(
                decision_model["selector_id"],
                selector_id,
                f"{label}: decision-model selector",
            )
            require_exact(
                decision_model["event_id"],
                event_id,
                f"{label}: decision-model event",
            )
            common_required_fields = decision_model["common_required_fields"]
            require_unique(
                common_required_fields,
                f"{label}: common required evidence fields",
            )
            axes = decision_model["axes"]
            require_unique(
                [axis["axis_id"] for axis in axes],
                f"{label}: decision axes",
            )
            for axis in axes:
                axis_label = f"{label}.{axis['axis_id']}"
                require_unique(
                    axis["derive_inputs"],
                    f"{axis_label}: derive inputs",
                )
                require(
                    all(
                        isinstance(value, str) and value
                        for value in (
                            axis["axis_id"],
                            axis["derive_operator"],
                            axis["source_path"],
                            axis["trust_source"],
                            axis["type"],
                            axis["values_from"],
                        )
                    ),
                    f"{axis_label}: empty or non-string decision-axis value",
                )
            evidence_variant_id_list = [
                item["evidence_variant_id"]
                for item in decision_model["evidence_variant_definitions"]
            ]
            require_unique(
                evidence_variant_id_list,
                f"{label}: evidence variant definitions",
            )
            evidence_variant_ids = set(evidence_variant_id_list)
            for variant in decision_model["evidence_variant_definitions"]:
                variant_label = f"{label}.{variant['evidence_variant_id']}"
                require_exact(
                    variant["forbidden_fields_rule"],
                    "FORBID_EVERY_OTHER_DECLARED_EVIDENCE_VARIANT_FIELD",
                    f"{variant_label}: forbidden-fields rule",
                )
                require_unique(
                    variant["required_fields"],
                    f"{variant_label}: required evidence fields",
                )
                require_unique(
                    variant["forbidden_fields"],
                    f"{variant_label}: forbidden evidence fields",
                )
                declared_required = set(common_required_fields) | set(
                    variant["required_fields"]
                )
                overlap = declared_required & set(variant["forbidden_fields"])
                require(
                    not overlap,
                    (
                        f"{variant_label}: required/forbidden evidence "
                        f"overlap {sorted(overlap)}"
                    ),
                )
                truth_conditions = variant["truth_conditions"]
                require(
                    truth_conditions,
                    f"{variant_label}: empty evidence truth conjunction",
                )
                require_unique(
                    truth_conditions,
                    f"{variant_label}: evidence truth conditions",
                )
                for condition in truth_conditions:
                    require(
                        isinstance(condition["field"], str)
                        and bool(condition["field"])
                        and isinstance(condition["operator"], str)
                        and bool(condition["operator"]),
                        (
                            f"{variant_label}: truth condition has an "
                            "empty or non-string field/operator"
                        ),
                    )
            require_exact(
                {transition_case["evidence_variant_id"] for transition_case in cases},
                evidence_variant_ids,
                f"{label}: evidence variant closure",
            )

            deadline_conditions = event["deadline_conditions"]["conditions"]
            deadline_ids = [
                condition["condition_id"] for condition in deadline_conditions
            ]
            require_unique(deadline_ids, f"{label}: deadline condition IDs")
            deadline_by_id = {
                condition["condition_id"]: condition
                for condition in deadline_conditions
            }
            for condition in deadline_conditions:
                require_exact(
                    set(condition),
                    {
                        "applies_to_semantic_case_ids",
                        "clock_authority",
                        "clock_incarnation_binding",
                        "comparison",
                        "condition_id",
                        "deadline_kind",
                        "evaluation_root",
                        "family_id",
                        "intent_root",
                        "key_cardinality",
                        "linearization_binding",
                        "purpose",
                        "source_or_intent",
                    },
                    f"{label}.{condition['condition_id']}: deadline shape",
                )
                require(
                    condition["comparison"] in {"AT_OR_AFTER", "STRICTLY_BEFORE"},
                    (
                        f"{label}.{condition['condition_id']}: "
                        "invalid deadline comparison"
                    ),
                )
                if not allow_known_incomplete:
                    require(
                        condition["applies_to_semantic_case_ids"],
                        (
                            f"{label}.{condition['condition_id']}: "
                            "empty deadline applicability"
                        ),
                    )
                require(
                    set(condition["applies_to_semantic_case_ids"]).issubset(
                        semantic_case_ids
                    ),
                    (
                        f"{label}.{condition['condition_id']}: "
                        "unknown deadline semantic case"
                    ),
                )
            case_count += len(cases)
            for transition_case in cases:
                case_label = f"{label}.{transition_case['semantic_case_id']}"
                edge_refs = transition_case["state_edge_refs"]
                require(edge_refs, f"{case_label}: no state edges")
                require_unique(edge_refs, f"{case_label}: state edge refs")
                require(
                    set(edge_refs).issubset(edge_by_id),
                    f"{case_label}: unknown state edge ref",
                )
                referenced_edge_ids.update(edge_refs)
                case_deadline_ids = transition_case["case_contract"][
                    "deadline_condition_ids"
                ]
                require_unique(
                    case_deadline_ids,
                    f"{case_label}: deadline condition refs",
                )
                require(
                    set(case_deadline_ids).issubset(deadline_by_id),
                    f"{case_label}: unknown deadline condition ref",
                )
                partition_refs = transition_case["case_contract"][
                    "partition_effect_refs"
                ]
                require_unique(
                    partition_refs,
                    f"{case_label}: partition refs",
                )
                require(
                    set(partition_refs).issubset(partition_by_id),
                    f"{case_label}: unknown partition ref",
                )
                for partition_id in partition_refs:
                    require(
                        transition_case["semantic_case_id"]
                        in partition_by_id[partition_id][
                            "applies_to_semantic_case_ids"
                        ],
                        f"{case_label}: asymmetric partition applicability",
                    )
            for deadline_id, condition in deadline_by_id.items():
                reverse_cases = {
                    transition_case["semantic_case_id"]
                    for transition_case in cases
                    if deadline_id
                    in transition_case["case_contract"]["deadline_condition_ids"]
                }
                require_exact(
                    set(condition["applies_to_semantic_case_ids"]),
                    reverse_cases,
                    f"{label}.{deadline_id}: deadline applicability closure",
                )

            for partition in partitions:
                partition_label = f"{label}.{partition['partition_id']}"
                domain_id = partition["state_domain"]
                require(
                    domain_id in domain_by_id,
                    f"{partition_label}: unknown state domain",
                )
                state_domain = domain_by_id[domain_id]
                require_exact(
                    partition["key_type"],
                    state_domain["key_type"],
                    f"{partition_label}: key type",
                )
                applies = partition["applies_to_semantic_case_ids"]
                require_unique(applies, f"{partition_label}: applies-to cases")
                require(
                    set(applies).issubset(semantic_case_ids),
                    f"{partition_label}: unknown applies-to case",
                )
                reverse_cases = {
                    transition_case["semantic_case_id"]
                    for transition_case in cases
                    if partition["partition_id"]
                    in transition_case["case_contract"]["partition_effect_refs"]
                }
                require_exact(
                    set(applies),
                    reverse_cases,
                    f"{partition_label}: partition applicability closure",
                )
                branch_ids = [branch["branch_id"] for branch in partition["branches"]]
                require_unique(branch_ids, f"{partition_label}: branch IDs")
                partition_branch_count += len(branch_ids)
                for branch in partition["branches"]:
                    require(
                        branch["from_state"] in state_domain["states"],
                        f"{partition_label}: unknown branch source state",
                    )
                    require(
                        branch["to_state"] in state_domain["states"],
                        f"{partition_label}: unknown branch target state",
                    )
                    require_exact(
                        branch["key_ref"],
                        state_domain["key_type"],
                        f"{partition_label}: branch key type",
                    )
                    transitions_by_domain[domain_id].add(
                        (branch["from_state"], branch["to_state"])
                    )

            sidecars = event["post_cas_sidecars"]
            sidecar_artifacts = [sidecar["artifact"] for sidecar in sidecars]
            require_unique(sidecar_artifacts, f"{label}: sidecars")
            require_exact(
                sidecar_artifacts.count(selector["generic_receipt"]),
                1,
                f"{label}: generic receipt count",
            )
            sidecar_count += len(sidecars)
            prior_artifacts: set[str] = set()
            for sidecar in sidecars:
                reference = sidecar["artifact"]
                _validate_artifact_ref(
                    reference,
                    artifacts,
                    f"{label}.sidecar",
                )
                dependencies = sidecar["depends_on"]
                require_unique(
                    dependencies,
                    f"{label}.{reference}: sidecar dependencies",
                )
                dependencies_by_case = sidecar.get(
                    "depends_on_by_semantic_case",
                    {},
                )
                require(
                    isinstance(dependencies_by_case, dict),
                    (
                        f"{label}.{reference}: case-specific dependencies "
                        "must be an object"
                    ),
                )
                if dependencies_by_case:
                    require_exact(
                        set(dependencies_by_case),
                        set(semantic_case_ids),
                        (f"{label}.{reference}: case-specific dependency coverage"),
                    )
                case_dependencies: set[str] = set()
                for case_id, case_values in dependencies_by_case.items():
                    require(
                        isinstance(case_values, list),
                        (
                            f"{label}.{reference}.{case_id}: "
                            "case-specific dependencies must be an array"
                        ),
                    )
                    require_unique(
                        case_values,
                        (f"{label}.{reference}.{case_id}: case-specific dependencies"),
                    )
                    require(
                        not (set(case_values) & set(dependencies)),
                        (
                            f"{label}.{reference}.{case_id}: "
                            "static/case dependency overlap"
                        ),
                    )
                    case_dependencies.update(case_values)
                require(
                    (set(dependencies) | case_dependencies).issubset(prior_artifacts),
                    f"{label}.{reference}: forward or external dependency",
                )
                prior_artifacts.add(reference)

            for collection in (
                event["consumes"],
                event["creates"],
                event["atomic_pre_cas_payloads"],
            ):
                role_artifact_pairs = [
                    (item.get("role"), item["artifact"]) for item in collection
                ]
                require_unique(
                    role_artifact_pairs,
                    f"{label}: artifact role pairs",
                )
                declared_roles = [item["role"] for item in collection if "role" in item]
                require_unique(
                    declared_roles,
                    f"{label}: artifact roles",
                )
                for item in collection:
                    _validate_artifact_ref(
                        item["artifact"],
                        artifacts,
                        f"{label}: artifact collection",
                    )

        require_exact(
            referenced_edge_ids,
            set(edge_by_id),
            f"{selector_id}: state-edge catalog use",
        )
        selector_without_state_declarations = copy.deepcopy(selector)
        for domain in selector_without_state_declarations["state_domains"]:
            domain.pop("states")
        referenced_state_bytes = canonical_bytes(selector_without_state_declarations)
        for state_domain in domains:
            for state in state_domain["states"]:
                require(
                    canonical_bytes(state) in referenced_state_bytes,
                    (
                        f"{selector_id}.{state_domain['state_domain']}: "
                        f"unreferenced state {state!r}"
                    ),
                )
        _validate_domain_state_reachability(
            selector_id=selector_id,
            state_domains=domains,
            transitions_by_domain=transitions_by_domain,
            allow_known_incomplete=allow_known_incomplete,
        )
        _validate_domain_terminal_liveness(
            selector_id=selector_id,
            state_domains=domains,
            transitions_by_domain=transitions_by_domain,
            allow_known_incomplete=allow_known_incomplete,
        )

    return (
        domain_count,
        event_count,
        case_count,
        partition_branch_count,
        sidecar_count,
    )


def _validate_global_key_registry(data: dict[str, Any]) -> None:
    expected = [
        {
            "coordinate_ref": (
                f"{selector['selector_id']}.{state_domain['state_domain']}.{join_field}"
            ),
            "selector_id": selector["selector_id"],
            "state_domain": state_domain["state_domain"],
            "field": join_field,
            "field_role": (
                "KEY_COORDINATE"
                if join_field in state_domain["key_coordinates"]
                else "CONTENT_ADDRESSED_JOIN_FIELD"
            ),
        }
        for selector in data["selectors"]
        for state_domain in selector["state_domains"]
        for join_field in state_domain["join_fields"]
    ]
    require_exact(
        data["global_key_coordinate_registry"],
        expected,
        "global key-coordinate registry",
    )
    require_unique(
        [item["coordinate_ref"] for item in data["global_key_coordinate_registry"]],
        "global key-coordinate registry references",
    )


def _validate_closure_commitments(data: dict[str, Any]) -> None:
    commitments = data["closure_commitments"]
    require_exact(
        set(commitments),
        {
            "algorithm",
            "artifact_registry_sha256",
            "canonicalization",
            "global_key_coordinate_registry_sha256",
            "resource_closure",
            "selector_semantic_digests",
            "structural_profiles_sha256",
        },
        "closure commitment fields",
    )
    require_exact(commitments["algorithm"], "SHA-256", "digest algorithm")
    require_exact(
        commitments["canonicalization"],
        "UTF8_JSON_SORTED_KEYS_NO_INSIGNIFICANT_WHITESPACE",
        "digest canonicalization",
    )
    expected_selector_digests = [
        {
            "selector_id": selector["selector_id"],
            "sha256": canonical_sha256(selector),
        }
        for selector in data["selectors"]
    ]
    require_exact(
        commitments["selector_semantic_digests"],
        expected_selector_digests,
        "selector semantic digests",
    )
    require_exact(
        commitments["artifact_registry_sha256"],
        canonical_sha256(data["artifacts"]),
        "artifact registry digest",
    )
    require_exact(
        commitments["global_key_coordinate_registry_sha256"],
        canonical_sha256(data["global_key_coordinate_registry"]),
        "global key-coordinate registry digest",
    )
    try:
        _, expected_resource_closure = derive_resource_closure(data)
    except ResourceClosureError as error:
        fail(f"resource closure derivation failed: {error}")
    require_exact(
        expected_resource_closure["per_kind_counts"],
        EXPECTED_RESOURCE_CLOSURE_PER_KIND_COUNTS,
        "resource closure kind counts",
    )
    require_exact(
        list(expected_resource_closure["per_kind_counts"]),
        list(RESOURCE_CLOSURE_KINDS),
        "resource closure kind order",
    )
    require_exact(
        expected_resource_closure["row_count"],
        EXPECTED_RESOURCE_CLOSURE_ROW_COUNT,
        "resource closure row count",
    )
    require_exact(
        commitments["resource_closure"],
        expected_resource_closure,
        "resource closure commitment",
    )
    profile_payload = {
        key: value
        for key, value in data.items()
        if key
        not in {
            "artifacts",
            "closure_commitments",
            "global_key_coordinate_registry",
            "selectors",
        }
    }
    require_exact(
        commitments["structural_profiles_sha256"],
        canonical_sha256(profile_payload),
        "structural profiles digest",
    )


def _observer_bridge_normalized_json(value: Any) -> Any:
    """Normalize the profile's JSON-only domain independently of probe code."""

    value_type = type(value)
    if value_type is dict:
        require(
            all(type(key) is str for key in value),
            "observer read/capture bridge profile contains a non-string key",
        )
        return {
            "$bridge_kind": "mapping",
            "entries": [
                [key, _observer_bridge_normalized_json(value[key])]
                for key in sorted(value)
            ],
        }
    if value_type is list:
        return {
            "$bridge_kind": "list",
            "items": [_observer_bridge_normalized_json(item) for item in value],
        }
    require(
        value is None or value_type in {bool, int, str},
        "observer read/capture bridge profile contains an unsupported scalar",
    )
    return value


def _observer_bridge_domain_kat(
    value: Any,
    *,
    domain: str,
) -> tuple[int, str, str]:
    normalized_raw = canonical_bytes(_observer_bridge_normalized_json(value))
    frame = (
        OBSERVER_READ_CAPTURE_BRIDGE_COMMITMENT_FRAME_PREFIX
        + b"\x00"
        + domain.encode("ascii")
        + b"\x00"
        + normalized_raw
    )
    return (
        len(normalized_raw),
        sha256(normalized_raw).hexdigest(),
        sha256(frame).hexdigest(),
    )


def _validate_observer_read_capture_bridge_profile(data: dict[str, Any]) -> None:
    """Pin the capability-to-historical-capture authority boundary."""

    profile = data["observer_read_capture_bridge_profile"]
    require(
        type(profile) is dict,
        "observer read/capture bridge profile must be a native JSON object",
    )
    profile_raw = canonical_bytes(profile)
    require_exact(
        (
            profile.get("schema"),
            len(profile_raw),
            sha256(profile_raw).hexdigest(),
        ),
        (
            OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_KAT["schema"],
            OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_KAT["canonical_byte_length"],
            OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_KAT["canonical_sha256"],
        ),
        "observer read/capture bridge profile standard-JSON KAT",
    )
    require_exact(
        _observer_bridge_domain_kat(
            profile,
            domain=OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_KAT["digest_domain"],
        ),
        (
            OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_KAT["normalized_byte_length"],
            OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_KAT["normalized_sha256"],
            OBSERVER_READ_CAPTURE_BRIDGE_PROFILE_KAT["digest"],
        ),
        "observer read/capture bridge profile normalized/domain KAT",
    )
    commitment = profile.get("canonical_commitment")
    require(
        type(commitment) is dict
        and set(commitment) == {"suite", "suite_digest", "suite_digest_domain"},
        "observer read/capture bridge profile commitment must be the exact triple",
    )
    suite = commitment["suite"]
    require(
        type(suite) is dict,
        "observer read/capture bridge commitment suite must be an object",
    )
    suite_raw = canonical_bytes(suite)
    require_exact(
        (
            suite.get("schema"),
            len(suite_raw),
            sha256(suite_raw).hexdigest(),
            commitment["suite_digest_domain"],
            commitment["suite_digest"],
        ),
        (
            OBSERVER_READ_CAPTURE_BRIDGE_SUITE_KAT["schema"],
            OBSERVER_READ_CAPTURE_BRIDGE_SUITE_KAT["canonical_byte_length"],
            OBSERVER_READ_CAPTURE_BRIDGE_SUITE_KAT["canonical_sha256"],
            OBSERVER_READ_CAPTURE_BRIDGE_SUITE_KAT["digest_domain"],
            OBSERVER_READ_CAPTURE_BRIDGE_SUITE_KAT["digest"],
        ),
        "observer read/capture bridge commitment suite KAT",
    )
    require_exact(
        _observer_bridge_domain_kat(
            suite,
            domain=OBSERVER_READ_CAPTURE_BRIDGE_SUITE_KAT["digest_domain"],
        ),
        (
            OBSERVER_READ_CAPTURE_BRIDGE_SUITE_KAT["normalized_byte_length"],
            OBSERVER_READ_CAPTURE_BRIDGE_SUITE_KAT["normalized_sha256"],
            OBSERVER_READ_CAPTURE_BRIDGE_SUITE_KAT["digest"],
        ),
        "observer read/capture bridge suite normalized/domain KAT",
    )


def _validate_joint_transactions(
    data: dict[str, Any],
    selectors: dict[str, dict[str, Any]],
    events: dict[tuple[str, str], dict[str, Any]],
) -> None:
    profiles = data["joint_selector_transaction_profiles"]
    joint_receipt = (
        "joint-selector-transaction-commit-receipt-type::"
        "JointSelectorTransactionCommitReceipt"
    )
    referenced_events: set[tuple[str, str]] = set()
    for profile_id, profile in profiles.items():
        require_exact(profile["profile_id"], profile_id, f"{profile_id}: ID")
        require_exact(
            profile["commit_receipt"],
            joint_receipt,
            f"{profile_id}: receipt",
        )
        participants = profile["participants"]
        declared_count = profile["declared_writing_participant_count"]
        require(
            isinstance(declared_count, int)
            and not isinstance(declared_count, bool)
            and declared_count >= 2,
            f"{profile_id}: declared writing participant count must be at least two",
        )
        require_exact(
            len(participants),
            declared_count,
            f"{profile_id}: declared writing participant count",
        )
        participant_keys = [
            (item["selector_id"], item["event_id"]) for item in participants
        ]
        require_unique(participant_keys, f"{profile_id}: participants")
        require_unique(
            [item["selector_id"] for item in participants],
            f"{profile_id}: participant selectors",
        )
        coordinator_count = 0
        participant_write_footprints: list[set[str]] = []
        for participant, key in zip(participants, participant_keys, strict=True):
            require(key in events, f"{profile_id}: missing participant {key}")
            event = events[key]
            require_exact(
                event.get("joint_selector_transaction_profile_ref"),
                profile_id,
                f"{profile_id}: participant profile ref",
            )
            declared_case_ids = participant["semantic_case_ids"]
            require_unique(
                declared_case_ids,
                f"{profile_id}: {key} semantic cases",
            )
            require(
                bool(declared_case_ids),
                f"{profile_id}: {key} has no declared semantic case",
            )
            event_case_ids = {
                item["semantic_case_id"] for item in event["transition_cases"]
            }
            require(
                set(declared_case_ids).issubset(event_case_ids),
                f"{profile_id}: {key} declares an unknown semantic case",
            )
            require_exact(
                event.get("joint_selector_transaction_semantic_case_ids"),
                declared_case_ids,
                f"{profile_id}: {key} event semantic-case scope",
            )
            selector = selectors[key[0]]
            require_exact(
                participant["expected_selector"],
                selector["selector"],
                f"{profile_id}: expected selector",
            )
            require_exact(
                participant["generic_receipt"],
                selector["generic_receipt"],
                f"{profile_id}: generic receipt",
            )
            write_footprint = {
                effect["resource"]
                for effect in event["common_case_effects"]
                if effect["action"] in {"RESERVE", "WRITE"}
            }
            require(
                bool(write_footprint),
                f"{profile_id}: {key} has no local write footprint",
            )
            require(
                all(resource.startswith(f"{key[0]}.") for resource in write_footprint),
                f"{profile_id}: {key} repeats a foreign participant write",
            )
            require_exact(
                set(event["common_case_mutates"]),
                write_footprint,
                f"{profile_id}: {key} mutation/write footprint",
            )
            require(
                all(
                    write_footprint.isdisjoint(prior)
                    for prior in participant_write_footprints
                ),
                f"{profile_id}: participant write footprints overlap",
            )
            participant_write_footprints.append(write_footprint)
            coordinator_count += sum(
                sidecar["artifact"] == joint_receipt
                for sidecar in event["post_cas_sidecars"]
            )
            referenced_events.add(key)
        require_exact(
            coordinator_count,
            1,
            f"{profile_id}: joint receipt coordinator count",
        )

    for key, event in events.items():
        profile_ref = event.get("joint_selector_transaction_profile_ref")
        if profile_ref is None:
            require(
                "joint_selector_transaction_semantic_case_ids" not in event,
                f"{key}: joint semantic-case scope has no profile",
            )
            continue
        require(
            profile_ref in profiles,
            f"{key}: unknown joint transaction profile",
        )
        require(
            key in referenced_events,
            f"{key}: profile reference is not a declared participant",
        )
        require(
            "joint_selector_transaction_semantic_case_ids" in event,
            f"{key}: joint profile lacks an exact semantic-case scope",
        )


def _validate_source_issuance_index(
    data: dict[str, Any],
    selectors: dict[str, dict[str, Any]],
    events: dict[tuple[str, str], dict[str, Any]],
    domains: dict[tuple[str, str], dict[str, Any]],
) -> None:
    """Require the generation-independent observer issuance barrier."""

    selector_id = "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX"
    require(selector_id in selectors, "observer source-issuance selector is missing")
    selector = selectors[selector_id]
    expected_selector = (
        "installed-observer-grant-source-issuance-index-selector-identity::"
        "InstalledObserverGrantSourceIssuanceIndexSelector"
    )
    expected_head = (
        "observer-grant-source-issuance-index-head-identity::"
        "ObserverGrantSourceIssuanceIndexHead"
    )
    expected_commit = (
        "observer-grant-source-issuance-index-commit-receipt-type::"
        "ObserverGrantSourceIssuanceIndexCommitReceipt"
    )
    expected_stable_key = (
        "observer-grant-source-issuance-stable-key-type::"
        "ObserverGrantSourceIssuanceStableKey"
    )
    expected_eligible_root_key = (
        "observer-grant-source-issuance-eligible-observer-root-key-type::"
        "ObserverGrantSourceIssuanceEligibleObserverRootKey"
    )
    expected_eligible_root_entry = (
        "observer-grant-source-issuance-eligible-observer-root-entry-type::"
        "ObserverGrantSourceIssuanceEligibleObserverRootEntry"
    )
    expected_enrollment_envelope = (
        "protected-observer-grant-source-issuance-observer-root-enrollment-"
        "envelope-type::"
        "ProtectedObserverGrantSourceIssuanceObserverRootEnrollmentEnvelope"
    )
    expected_enrollment_projection = (
        "observer-grant-source-issuance-observer-root-enrollment-projection-"
        "type::ObserverGrantSourceIssuanceObserverRootEnrollmentProjection"
    )
    expected_enrollment_manifest = (
        "observer-grant-source-issuance-observer-root-enrollment-publication-"
        "manifest-type::"
        "ObserverGrantSourceIssuanceObserverRootEnrollmentPublicationManifest"
    )
    require_exact(selector["selector"], expected_selector, "source-index selector")
    require_exact(selector["root"], expected_head, "source-index head")
    require_exact(
        selector["generic_receipt"],
        expected_commit,
        "source-index generic commit receipt",
    )

    root = domains[(selector_id, "ROOT")]
    require_exact(
        set(root["states"]),
        {
            "ABSENT_NEVER_USED",
            "SOURCE_ISSUANCE_OPEN",
            "SOURCE_ISSUANCE_FROZEN_PERMANENTLY_RETIRED",
        },
        "source-index phase closure",
    )
    require_exact(
        root["initial_state"],
        "ABSENT_NEVER_USED",
        "source-index initial phase",
    )
    require_exact(
        root["terminal_states"],
        ["SOURCE_ISSUANCE_FROZEN_PERMANENTLY_RETIRED"],
        "source-index terminal phase",
    )
    require_exact(
        root["key_coordinates"],
        [
            "AUTHORITY_TRANSACTION_DOMAIN_KEY",
            "SOURCE_LOGICAL_SESSION_ID",
            "SOURCE_SESSION_KIND",
        ],
        "source-index stable namespace key",
    )
    require(
        "SOURCE_SESSION_GENERATION" not in root["join_fields"],
        "source-index namespace is generation-scoped",
    )

    entries = domains[(selector_id, "ISSUANCE_ENTRY")]
    require_exact(
        entries["key_type"],
        expected_stable_key,
        "source-index stable entry key",
    )
    require_exact(
        set(entries["states"]),
        {
            "ABSENT",
            "CANCELED_BEFORE_ISSUANCE",
            "CHALLENGE_ISSUED",
        },
        "source-index entry-kind closure",
    )
    require_exact(
        set(entries["terminal_states"]),
        {"CANCELED_BEFORE_ISSUANCE", "CHALLENGE_ISSUED"},
        "source-index append-only terminal members",
    )
    require(
        "SOURCE_SESSION_GENERATION" not in entries["key_coordinates"],
        "source-index stable entry key includes a generation",
    )
    require_exact(
        entries["key_coordinates"],
        [
            "AUTHORITY_REALM_KEY",
            "SOURCE_SESSION_KIND",
            "SOURCE_LOGICAL_SESSION_ID",
            "AUTHENTICATED_REQUESTER_PRINCIPAL",
            "OBSERVER_ROOT_INCARNATION",
            "REQUEST_OPERATION",
            "REQUEST_KIND",
            "LOGICAL_TARGET_KEY",
        ],
        "source-index stable entry-key projection",
    )
    eligible_roots = domains[(selector_id, "ELIGIBLE_OBSERVER_ROOT_ENTRY")]
    require_exact(
        eligible_roots["key_type"],
        expected_eligible_root_key,
        "source-index eligible-root key",
    )
    require_exact(
        eligible_roots["states"],
        [
            "ABSENT",
            "CANCELED_BEFORE_SOURCE_CONFIRMATION",
            "ELIGIBLE",
            "FROZEN_BEFORE_SOURCE_CONFIRMATION",
            "PENDING_ANCHOR_ENROLLMENT",
        ],
        "source-index eligible-root state closure",
    )
    require_exact(
        eligible_roots["terminal_states"],
        [
            "CANCELED_BEFORE_SOURCE_CONFIRMATION",
            "ELIGIBLE",
            "FROZEN_BEFORE_SOURCE_CONFIRMATION",
        ],
        "source-index eligible-root retained terminal states",
    )
    require_exact(
        eligible_roots["key_coordinates"],
        [
            "AUTHORITY_REALM_KEY",
            "SOURCE_SESSION_KIND",
            "SOURCE_LOGICAL_SESSION_ID",
            "OBSERVER_ROOT_KEY",
            "OBSERVER_ROOT_INCARNATION",
        ],
        "source-index eligible-root stable key",
    )
    require(
        "SOURCE_SESSION_GENERATION" not in eligible_roots["join_fields"],
        "source-index eligible-root registry is generation-scoped",
    )

    edge_by_id = {edge["edge_id"]: edge for edge in selector["state_edge_catalog"]}

    def event_edges(
        event_id: str,
        state_domain: str,
    ) -> set[tuple[str, str]]:
        event = events[(selector_id, event_id)]
        return {
            (
                edge_by_id[edge_ref]["from_state"],
                edge_by_id[edge_ref]["to_state"],
            )
            for case in event["transition_cases"]
            for edge_ref in case["state_edge_refs"]
            if edge_by_id[edge_ref]["state_domain"] == state_domain
        }

    genesis_event = (
        "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX_GENESIS_FROM_SOURCE_LINEAGE_REGISTRATION"
    )
    publish_anchor_eligibility_event = (
        "PUBLISH_OBSERVER_ROOT_CHALLENGE_EXPOSURE_ANCHOR_ENROLLMENT_ELIGIBILITY"
    )
    enrollment_event = "ENROLL_OBSERVER_ROOT_IN_SOURCE_ISSUANCE_INDEX"
    cancel_anchor_eligibility_event = (
        "CANCEL_PENDING_ANCHOR_ENROLLMENT_ELIGIBILITY_AFTER_CUTOFF"
    )
    issue_event = "ISSUE_OBSERVER_GRANT_REQUEST_FRESHNESS_CHALLENGE"
    cancel_event = "CANCEL_OBSERVER_GRANT_REQUEST_BEFORE_ACCEPTANCE"
    freeze_event = "FINALIZE_SOURCE_LOGICAL_SESSION_PERMANENT_RETIREMENT"
    require_exact(
        {event["event_id"] for event in selector["events"]},
        {
            genesis_event,
            publish_anchor_eligibility_event,
            enrollment_event,
            cancel_anchor_eligibility_event,
            issue_event,
            cancel_event,
            freeze_event,
        },
        "source-index event closure",
    )
    require_exact(
        event_edges(genesis_event, "ROOT"),
        {("ABSENT_NEVER_USED", "SOURCE_ISSUANCE_OPEN")},
        "source-index genesis edge",
    )
    require_exact(
        event_edges(enrollment_event, "ELIGIBLE_OBSERVER_ROOT_ENTRY"),
        {
            ("ABSENT", "ELIGIBLE"),
            ("PENDING_ANCHOR_ENROLLMENT", "ELIGIBLE"),
        },
        "source-index eligible-root enrollment edges",
    )
    require_exact(
        event_edges(
            publish_anchor_eligibility_event,
            "ELIGIBLE_OBSERVER_ROOT_ENTRY",
        ),
        {("ABSENT", "PENDING_ANCHOR_ENROLLMENT")},
        "source-index pending anchor-enrollment publication edge",
    )
    require_exact(
        event_edges(
            cancel_anchor_eligibility_event,
            "ELIGIBLE_OBSERVER_ROOT_ENTRY",
        ),
        {
            (
                "PENDING_ANCHOR_ENROLLMENT",
                "CANCELED_BEFORE_SOURCE_CONFIRMATION",
            )
        },
        "source-index pending anchor-enrollment cancellation edge",
    )
    require_exact(
        event_edges(issue_event, "ISSUANCE_ENTRY"),
        {("ABSENT", "CHALLENGE_ISSUED")},
        "source-index challenge append edge",
    )
    require_exact(
        event_edges(cancel_event, "ISSUANCE_ENTRY"),
        {("ABSENT", "CANCELED_BEFORE_ISSUANCE")},
        "source-index absent-cancellation burn edge",
    )
    require_exact(
        event_edges(freeze_event, "ROOT"),
        {
            (
                "SOURCE_ISSUANCE_OPEN",
                "SOURCE_ISSUANCE_FROZEN_PERMANENTLY_RETIRED",
            )
        },
        "source-index final freeze edge",
    )

    enrollment = events[(selector_id, enrollment_event)]
    enrollment_contract = enrollment["authority_transaction_contract"]
    require_exact(
        set(enrollment_contract["write_roles"]),
        {
            "AUTHORITY_TRANSACTION_DOMAIN_STATE",
            "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX",
        },
        "source-index eligible-root enrollment write footprint",
    )
    require(
        all(
            {
                "AUTHORITY_TRANSACTION_DOMAIN_STATE",
                "LOCAL_SECURITY_ENFORCEMENT",
                "LOGICAL_SESSION_LINEAGE",
                "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX",
            }.issubset(variant["participant_roles"])
            for variant in enrollment_contract["participant_role_variants"]
        ),
        "source-index enrollment omits lineage or security currentness",
    )
    enrollment_created = {item["artifact"] for item in enrollment["creates"]}
    require(
        expected_eligible_root_entry in enrollment_created,
        "source-index enrollment omits its immutable eligible-root candidate",
    )
    enrollment_sidecars = {item["artifact"] for item in enrollment["post_cas_sidecars"]}
    require(
        {
            expected_enrollment_envelope,
            expected_enrollment_projection,
            expected_enrollment_manifest,
        }.issubset(enrollment_sidecars),
        "source-index enrollment publication hierarchy is incomplete",
    )
    require(
        {
            "SOURCE_ONLY_PROFILE",
            "INDEPENDENT_ANCHOR_PROFILE",
        }
        == {
            item["evidence_variant_id"]
            for item in enrollment["decision_model"]["evidence_variant_definitions"]
        },
        "source-index enrollment availability-profile closure",
    )

    source_role = "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX"
    require_exact(
        data["joint_selector_transaction_profiles"]["JTX_SOURCE_LINEAGE_REGISTRATION"][
            "declared_writing_participant_count"
        ],
        3,
        "source-index registration writer count",
    )
    require_exact(
        data["joint_selector_transaction_profiles"]["JTX_OBSERVER_TARGET_CHALLENGE"][
            "declared_writing_participant_count"
        ],
        3,
        "source-index challenge writer count",
    )
    require_exact(
        data["joint_selector_transaction_profiles"][
            "JTX_OBSERVER_SOURCE_ISSUANCE_CANCEL_ABSENT"
        ]["declared_writing_participant_count"],
        2,
        "source-index absent-cancellation writer count",
    )

    for key in (
        (
            "LOGICAL_SESSION_NAMESPACE_REGISTRY",
            "REGISTER_SOURCE_LOGICAL_SESSION_LINEAGE",
        ),
        (
            "LOGICAL_SESSION_GENERATION_LINEAGE",
            "LOGICAL_SESSION_GENERATION_LINEAGE_GENESIS_FROM_SERVER_AUTHORITY",
        ),
        (selector_id, genesis_event),
        ("OBSERVER_AUTHORIZATION", issue_event),
        ("OBSERVER_ATTACHMENT_TARGET_HISTORY", issue_event),
        (selector_id, issue_event),
        ("OBSERVER_AUTHORIZATION", cancel_event),
        (selector_id, cancel_event),
        (
            "LOGICAL_SESSION_GENERATION_LINEAGE",
            freeze_event,
        ),
        (
            "LOGICAL_SESSION_NAMESPACE_REGISTRY",
            freeze_event,
        ),
        (selector_id, freeze_event),
    ):
        require(key in events, f"source-index transaction event is missing: {key}")
        contract = events[key]["authority_transaction_contract"]
        require(
            source_role in contract["write_roles"],
            f"{key}: source-index writer is missing",
        )

    acceptance_binding = (
        "SOURCE_ISSUANCE_INDEX_OPEN_AND_EXACT_CHALLENGE_MEMBER_MATCHES_"
        "LOCAL_SLOT_STABLE_KEY_GENERATION_AND_COMMITMENT"
    )
    for event_id in (
        "ATTACH_NEW_GRANT_LINEAGE",
        "BEGIN_GRANT_RENEWAL",
        "REATTACH_FROM_TERMINAL_GRANT",
    ):
        for owner in ("OBSERVER_AUTHORIZATION", "OBSERVER_ATTACHMENT_TARGET_HISTORY"):
            key = (owner, event_id)
            event = events[key]
            contract = event["authority_transaction_contract"]
            require(
                all(
                    source_role in variant["participant_roles"]
                    and source_role not in variant["write_roles"]
                    for variant in contract["participant_role_variants"]
                ),
                f"{key}: source index is not an exact read-only participant",
            )
            require(
                source_role not in contract["write_roles"],
                f"{key}: acceptance mutates the source index",
            )
            consumed = {item["artifact"] for item in event["consumes"]}
            require(
                {expected_selector, expected_head}.issubset(consumed),
                f"{key}: acceptance omits source-index expected state",
            )
            require(
                acceptance_binding in event["pre_cas_content"]["required_bindings"],
                f"{key}: acceptance omits source-index member equality",
            )

    observer_cancel = events[("OBSERVER_AUTHORIZATION", cancel_event)]
    absent_case_id = (
        "FROM_GRANT_REQUEST_FRESHNESS_SLOT_ABSENT__ROOT_ACTIVE_"
        "TO_GRANT_REQUEST_FRESHNESS_SLOT_CANCELED_UNUSED__ROOT_ACTIVE"
    )
    cancel_case_writes = observer_cancel["authority_transaction_contract"][
        "write_roles_by_semantic_case"
    ]
    require(
        source_role in cancel_case_writes[absent_case_id]
        and all(
            source_role not in roles
            for case_id, roles in cancel_case_writes.items()
            if case_id != absent_case_id
        ),
        "observer cancellation does not distinguish burn from exact-member close",
    )
    require_exact(
        observer_cancel["joint_selector_transaction_semantic_case_ids"],
        [absent_case_id],
        "observer absent-cancellation joint scope",
    )

    required_bindings = {
        (selector_id, genesis_event): (
            "TYPED_SOURCE_INDEX_ABSENCE_NEVER_USED_PROOF_AND_FIXED_EMPTY_ROOT"
        ),
        (selector_id, publish_anchor_eligibility_event): (
            "PENDING_ELIGIBILITY_ANCHOR_ENROLLMENT_AND_SOURCE_CONFIRMATION_"
            "BIND_THE_SAME_RELATION_DIGEST_AND_CAPTURED_CUTOFF"
        ),
        (selector_id, enrollment_event): (
            "OPEN_SOURCE_INDEX_ELIGIBLE_ROOT_NONMEMBERSHIP_AND_EXACT_"
            "REGISTERED_OBSERVER_ROOT_ELIGIBILITY"
        ),
        (selector_id, cancel_anchor_eligibility_event): (
            "SAME_KEY_CONFIRMATION_AND_CANCELLATION_CAS_EXACTLY_ONE_WINS"
        ),
        (selector_id, issue_event): (
            "STABLE_KEY_NONMEMBERSHIP_AND_LOCAL_AVAILABLE_SLOT_APPEND_ATOMIC"
        ),
        (selector_id, cancel_event): (
            "ABSENT_INTENT_CANCELLATION_APPENDS_CANCELED_BEFORE_ISSUANCE_"
            "AND_LOCAL_TOMBSTONE_ATOMICALLY"
        ),
        (selector_id, freeze_event): (
            "COMPLETE_GENERATION_SLOT_INDEX_BIJECTION_AND_EMPTY_EXPOSURE_IN_FLIGHT_SET"
        ),
    }
    for key, binding in required_bindings.items():
        require(
            binding in events[key]["pre_cas_content"]["required_bindings"],
            f"{key}: missing source-index invariant {binding}",
        )

    closure_audience = (
        "observer-grant-source-closure-audience-assessment-type::"
        "ObserverGrantSourceClosureAudienceAssessment"
    )
    freeze_consumed = {
        item["artifact"] for item in events[(selector_id, freeze_event)]["consumes"]
    }
    require(
        closure_audience in freeze_consumed,
        "source-index freeze omits the retained-root closure audience",
    )
    require(
        (
            "COMPLETE_RETAINED_ELIGIBLE_OBSERVER_ROOT_SET_BIJECTS_ALL_SOURCE_"
            "INDEX_ROOT_ENROLLMENT_HIERARCHIES_AND_DEFINES_THE_ONLY_CLOSURE_AUDIENCE"
        )
        in events[(selector_id, freeze_event)]["pre_cas_content"]["required_bindings"],
        "source-index freeze does not derive closure from retained enrollment",
    )
    prepare = events[("OBSERVER_ADMISSION", "PREPARE_OBSERVER_GRANT_REQUEST_INTENT")]
    prepare_consumed = {item["artifact"] for item in prepare["consumes"]}
    require(
        {
            expected_enrollment_envelope,
            expected_enrollment_projection,
            expected_enrollment_manifest,
        }.issubset(prepare_consumed),
        "local PREPARE omits the verified source enrollment hierarchy",
    )
    require(
        (
            "VERIFIED_SOURCE_INDEX_ROOT_ENROLLMENT_HIERARCHY_MATCHES_SOURCE_"
            "NAMESPACE_OBSERVER_ROOT_INCARNATION_AVAILABILITY_PROFILE_AND_INDEX_LINEAGE"
        )
        in prepare["pre_cas_content"]["required_bindings"],
        "local PREPARE does not bind exact source-root enrollment",
    )
    retirement_profile = data["source_logical_session_retirement_profile"][
        "source_issuance_index_finalization"
    ]
    require(
        "CURRENT_ADR009_REGISTRY" in retirement_profile["closure_audience_derivation"]
        and "RETAINED_SOURCE_INDEX_ELIGIBLE_OBSERVER_ROOT_SET"
        in retirement_profile["closure_audience_derivation"],
        "source closure audience can drift to a current external registry",
    )


def _validate_simulation_subresource_architecture(
    data: dict[str, Any],
    selectors: dict[str, dict[str, Any]],
    events: dict[tuple[str, str], dict[str, Any]],
    domains: dict[tuple[str, str], dict[str, Any]],
    artifacts: set[str],
) -> None:
    selector_id = "SIMULATION_SESSION_STATE"
    selector = selectors[selector_id]
    profile = _require_closed_shape(
        data["simulation_session_state_profile"],
        required={
            "active_authority",
            "owned_bounded_registries",
            "pending_parent_authority",
            "plant_fields_and_authority",
            "provenance",
            "retirement",
            "root",
            "selector",
            "states",
            "subresource_authority",
            "subresource_dependency_dag",
            "subresource_event_kinds",
            "subresource_idempotency",
            "subresource_member_lifecycle",
            "subresource_qualification_bounds",
            "subresource_receipt_dag",
            "terminal_cause_policy",
            "unknown_default_state_or_operation",
        },
        allowed={
            "active_authority",
            "owned_bounded_registries",
            "pending_parent_authority",
            "plant_fields_and_authority",
            "provenance",
            "retirement",
            "root",
            "selector",
            "states",
            "subresource_authority",
            "subresource_dependency_dag",
            "subresource_event_kinds",
            "subresource_idempotency",
            "subresource_member_lifecycle",
            "subresource_qualification_bounds",
            "subresource_receipt_dag",
            "terminal_cause_policy",
            "unknown_default_state_or_operation",
        },
        label="simulation_session_state_profile",
    )
    require_exact(
        profile["selector"], selector["selector"], "simulation profile selector"
    )
    require_exact(profile["root"], selector["root"], "simulation profile root")
    require_exact(
        profile["states"],
        ["PENDING_PARENT_CONFIRMATION", "ACTIVE", "RETIRED_DRAIN_ONLY", "TERMINAL"],
        "simulation profile lifecycle states",
    )
    require_exact(
        set(profile["states"]),
        set(domains[(selector_id, "ROOT")]["states"]),
        "simulation profile/root state parity",
    )
    require_exact(
        profile["pending_parent_authority"],
        "NONE",
        "simulation pending-parent authority",
    )
    require_exact(
        profile["plant_fields_and_authority"],
        "STRUCTURALLY_FORBIDDEN",
        "simulation plant authority boundary",
    )
    require_exact(
        profile["provenance"],
        {
            "calibrated_posterior": False,
            "is_simulation_output": True,
            "paper_reproduction_or_calibration_claim": "FORBIDDEN",
        },
        "simulation provenance boundary",
    )
    require_exact(
        profile["unknown_default_state_or_operation"],
        "REJECT",
        "simulation unknown/default policy",
    )

    registry_domains = [
        "OPERATION_JOB",
        "OUTPUT_STREAM",
        "RESOURCE_GRANT",
        "DELIVERY_OBLIGATION",
        "OBSERVER_OBLIGATION",
    ]
    require_exact(
        profile["owned_bounded_registries"],
        registry_domains,
        "simulation owned registry order",
    )
    require(
        all((selector_id, domain) in domains for domain in registry_domains),
        "simulation profile names an absent owned registry",
    )
    require_exact(
        profile["subresource_authority"],
        {
            "active_authorizer": (
                "EXACT_CONFIGURED_SIMULATION_RESPONDER_PRINCIPAL_AND_BOUNDED_"
                "SIMULATION_OPERATION_GRANT"
            ),
            "drain_only": ("EXACT_REPLAY_QUERY_OR_RESTRICTIVE_TERMINALIZATION_ONLY"),
            "grant_scope": (
                "EXACT_EVENT_RESOURCE_KEY_DEPENDENCIES_SEQUENCE_QUOTA_DEADLINE_"
                "AND_RETAINED_RESERVE"
            ),
            "parent_compare": (
                "CURRENT_GENERATION_LIVE_FOR_ACTIVE_OR_FROZEN_PARENT_"
                "RETIREMENT_EVIDENCE_FOR_DRAIN_ONLY"
            ),
            "pending_parent": "NO_SUBRESOURCE_OR_OUTPUT_AUTHORITY",
            "widening_and_progress": "ACTIVE_ONLY",
        },
        "simulation subresource authority",
    )
    require_exact(
        profile["subresource_dependency_dag"],
        {
            "cycle_or_unqualified_edge": "REJECT_BEFORE_CAS",
            "dependency_set": "IMMUTABLE_PER_MEMBER",
            "insertion_fit_rule": (
                "EVERY_REACHABLE_TERMINAL_CASCADE_IN_THE_RESULTING_DAG_FITS_"
                "THE_QUALIFIED_MEMBER_BYTE_AND_RESTRICTIVE_RESERVE_BOUNDS"
            ),
            "reverse_index": "CANONICAL_DERIVATION_IN_THE_SAME_SIMULATION_HEAD",
            "terminal_cascade": (
                "EXACT_TRANSITIVE_DEPENDENT_CLOSURE_IN_LEXICOGRAPHICALLY_"
                "LEAST_REVERSE_TOPOLOGICAL_ORDER"
            ),
        },
        "simulation dependency DAG",
    )
    idempotency = _require_closed_shape(
        profile["subresource_idempotency"],
        required={
            "crash_after_cas_before_manifests",
            "crash_before_cas",
            "key",
            "key_coordinates",
            "operation_index_entry",
            "reply_loss",
            "same_operation_changed_event_bytes_key_dependency_sequence_quota_or_cause",
        },
        allowed={
            "crash_after_cas_before_manifests",
            "crash_before_cas",
            "key",
            "key_coordinates",
            "operation_index_entry",
            "reply_loss",
            "same_operation_changed_event_bytes_key_dependency_sequence_quota_or_cause",
        },
        label="simulation_session_state_profile.subresource_idempotency",
    )
    require_exact(
        idempotency["key_coordinates"],
        ["AUTHORITY_TRANSACTION_DOMAIN_KEY", "SESSION_REF", "OPERATION_ID"],
        "simulation subresource operation key",
    )
    for field in ("key", "operation_index_entry"):
        _validate_artifact_ref(
            idempotency[field],
            artifacts,
            f"simulation subresource idempotency {field}",
        )
    require_exact(
        idempotency[
            "same_operation_changed_event_bytes_key_dependency_sequence_quota_or_cause"
        ],
        "REJECT",
        "simulation changed-operation replay",
    )
    require_exact(
        profile["subresource_qualification_bounds"],
        {
            "bounded_dimensions": [
                "DEPENDENCY_CASCADE_MEMBERS_AND_BYTES",
                "DELIVERY_ADVANCES",
                "FACT_CANDIDATE_RECEIPT_AND_MANIFEST_BYTES",
                "GRANT_QUOTA_AND_DEADLINE",
                "JOB_PROGRESS_COUNT",
                "OPERATION_INDEX_RETENTION",
                "PER_REGISTRY_MEMBERS_AND_BYTES",
                "STREAM_ITEMS_AND_BYTES",
                "TRANSACTION_COMMIT_POSITION_WIDTH",
            ],
            "checked_arithmetic": "NO_WRAP",
            "equality_at_bound": "PASS",
            "exhaustion": "REJECT_BEFORE_MUTATION",
            "genesis_reserve": (
                "FIXED_RETIREMENT_FINALIZATION_BUNDLES_AND_BASE_CLOSURE_PARTITION"
            ),
            "per_member_reserve": (
                "MAXIMUM_TERMINAL_OPERATION_INDEX_ENTRY_RECEIPT_TOMBSTONE_AND_"
                "INCREMENTAL_RETIREMENT_PARTITION_COST"
            ),
            "terminal_tombstone_operation_identity_and_restrictive_reserve": (
                "NEVER_EVICTED_OR_BORROWED_TO_ADMIT_WORK"
            ),
        },
        "simulation subresource qualification bounds",
    )
    expected_lifecycle = {
        "DELIVERY_OBLIGATION": [
            "ABSENT_TO_LIVE",
            "LIVE_TO_CHECKED_NEXT_LIVE",
            "LIVE_TO_TERMINAL",
        ],
        "OBSERVER_OBLIGATION": ["ABSENT_TO_LIVE", "LIVE_TO_TERMINAL"],
        "OPERATION_JOB": [
            "ABSENT_TO_PENDING",
            "PENDING_TO_RUNNING",
            "RUNNING_TO_CHECKED_NEXT_RUNNING",
            "PENDING_OR_RUNNING_TO_TERMINAL",
        ],
        "OUTPUT_STREAM": [
            "ABSENT_TO_OPEN",
            "OPEN_TO_CHECKED_NEXT_OPEN",
            "OPEN_TO_TERMINAL",
        ],
        "RESOURCE_GRANT": [
            "ABSENT_TO_LIVE",
            "LIVE_POSITIVE_REMAINDER_TO_CHECKED_NEXT_LIVE",
            "LIVE_TO_TERMINAL",
        ],
    }
    require_exact(
        profile["subresource_member_lifecycle"],
        expected_lifecycle,
        "simulation subresource member lifecycle",
    )
    expected_receipt_dag = [
        "AUTHORITY_TRANSACTION_COMMIT_RECEIPT",
        "SIMULATION_SESSION_STATE_COMMIT_RECEIPT",
        "SIMULATION_SESSION_SUBRESOURCE_COMMIT_RECEIPT",
        "AUTHORITY_TRANSACTION_PERSISTENCE_MANIFEST",
        "SIMULATION_SESSION_SUBRESOURCE_PERSISTENCE_MANIFEST",
    ]
    require_exact(
        profile["subresource_receipt_dag"],
        expected_receipt_dag,
        "simulation subresource receipt DAG",
    )
    terminal_policy = profile["terminal_cause_policy"]
    require_exact(
        terminal_policy["caller_selected_cause"],
        "FORBIDDEN",
        "simulation caller-selected terminal cause",
    )
    require_exact(
        terminal_policy["dependent_cause_by_resource_class"],
        {
            "DELIVERY_OBLIGATION": "DELIVERY_CANCELED",
            "OBSERVER_OBLIGATION": "OBSERVER_REFERENCE_RELEASED",
            "OPERATION_JOB": "JOB_CANCELED",
            "OUTPUT_STREAM": "STREAM_CLOSED",
            "RESOURCE_GRANT": "GRANT_REVOKED",
        },
        "simulation dependent terminal causes",
    )
    require_exact(
        terminal_policy["terminal_cause_union"],
        [
            "DELIVERY_CANCELED",
            "DELIVERY_COMPLETED",
            "DELIVERY_FAILED",
            "GRANT_EXHAUSTED",
            "GRANT_EXPIRED",
            "GRANT_REVOKED",
            "JOB_CANCELED",
            "JOB_COMPLETED",
            "JOB_FAILED",
            "OBSERVER_REFERENCE_RELEASED",
            "SESSION_RETIREMENT",
            "STREAM_CLOSED",
        ],
        "simulation terminal-cause union",
    )
    _validate_artifact_ref(
        terminal_policy["policy"],
        artifacts,
        "simulation terminal-cause policy",
    )

    expected_subresource_events = [
        "CREATE_SIMULATION_JOB",
        "START_SIMULATION_JOB",
        "RECORD_SIMULATION_JOB_PROGRESS",
        "TERMINALIZE_SIMULATION_JOB",
        "OPEN_SIMULATION_OUTPUT_STREAM",
        "APPEND_SIMULATION_OUTPUT_STREAM_ITEM",
        "TERMINALIZE_SIMULATION_OUTPUT_STREAM",
        "ISSUE_SIMULATION_RESOURCE_GRANT",
        "CONSUME_SIMULATION_RESOURCE_GRANT_QUOTA",
        "TERMINALIZE_SIMULATION_RESOURCE_GRANT",
        "CREATE_SIMULATION_SOURCE_LOCAL_DELIVERY",
        "ADVANCE_SIMULATION_SOURCE_LOCAL_DELIVERY",
        "TERMINALIZE_SIMULATION_SOURCE_LOCAL_DELIVERY",
        "REGISTER_SIMULATION_SOURCE_LOCAL_OBSERVER_REFERENCE",
        "TERMINALIZE_SIMULATION_SOURCE_LOCAL_OBSERVER_REFERENCE",
    ]
    require_exact(
        profile["subresource_event_kinds"],
        expected_subresource_events,
        "simulation subresource event surface",
    )
    lifecycle_events = {
        "SIMULATION_SESSION_STATE_GENESIS_FROM_GENERATION_CREATION",
        "ACTIVATE_SIMULATION_SESSION_AFTER_PARENT_CONFIRMATION",
        "RETIRE_SIMULATION_SESSION_GENERATION",
        "FINALIZE_SIMULATION_SESSION_GENERATION",
    }
    require_exact(
        {event["event_id"] for event in selector["events"]},
        lifecycle_events | set(expected_subresource_events),
        "simulation complete event surface",
    )

    edge_by_id = {edge["edge_id"]: edge for edge in selector["state_edge_catalog"]}

    def event_edges(event: dict[str, Any], domain: str) -> set[tuple[str, str]]:
        return {
            (edge_by_id[edge_ref]["from_state"], edge_by_id[edge_ref]["to_state"])
            for case in event["transition_cases"]
            for edge_ref in case["state_edge_refs"]
            if edge_by_id[edge_ref]["state_domain"] == domain
        }

    subresource_domain_by_event = {
        "CREATE_SIMULATION_JOB": "OPERATION_JOB",
        "START_SIMULATION_JOB": "OPERATION_JOB",
        "RECORD_SIMULATION_JOB_PROGRESS": "OPERATION_JOB",
        "TERMINALIZE_SIMULATION_JOB": "OPERATION_JOB",
        "OPEN_SIMULATION_OUTPUT_STREAM": "OUTPUT_STREAM",
        "APPEND_SIMULATION_OUTPUT_STREAM_ITEM": "OUTPUT_STREAM",
        "TERMINALIZE_SIMULATION_OUTPUT_STREAM": "OUTPUT_STREAM",
        "ISSUE_SIMULATION_RESOURCE_GRANT": "RESOURCE_GRANT",
        "CONSUME_SIMULATION_RESOURCE_GRANT_QUOTA": "RESOURCE_GRANT",
        "TERMINALIZE_SIMULATION_RESOURCE_GRANT": "RESOURCE_GRANT",
        "CREATE_SIMULATION_SOURCE_LOCAL_DELIVERY": "DELIVERY_OBLIGATION",
        "ADVANCE_SIMULATION_SOURCE_LOCAL_DELIVERY": "DELIVERY_OBLIGATION",
        "TERMINALIZE_SIMULATION_SOURCE_LOCAL_DELIVERY": "DELIVERY_OBLIGATION",
        "REGISTER_SIMULATION_SOURCE_LOCAL_OBSERVER_REFERENCE": ("OBSERVER_OBLIGATION"),
        "TERMINALIZE_SIMULATION_SOURCE_LOCAL_OBSERVER_REFERENCE": (
            "OBSERVER_OBLIGATION"
        ),
    }
    terminal_events = {
        event_id
        for event_id in expected_subresource_events
        if event_id.startswith("TERMINALIZE_")
    }
    common_bindings = {
        "CHECKED_COUNTER_SEQUENCE_QUOTA_AND_RESERVE_ARITHMETIC_WITHOUT_WRAP",
        "CONDITION_COMPARE_SIMULATION_PARENT_AUTHORITY_DOMAIN_AND_SECURITY_IN_ONE_TRANSACTION",
        "DEPENDENCY_KEYS_RESOLVE_TO_REQUIRED_NONTERMINAL_MEMBERS_IN_THE_SAME_EXPECTED_HEAD",
        "EXACT_CONFIGURED_SIMULATION_RESPONDER_PRINCIPAL_AND_BOUNDED_OPERATION_GRANT",
        "EXACT_NEVER_REUSED_SUBRESOURCE_OPERATION_KEY",
        "EXACT_PARENT_CURRENTNESS_EVIDENCE_BRANCH",
        "EXACT_RESOURCE_CLASS_KEY_PRIOR_MEMBERSHIP_STATE_AND_DEPENDENT_SET",
        "RECEIPT_FREE_SUBRESOURCE_CANDIDATE_BINDS_FACT_CONDITION_AND_CASCADE_AND_EXCLUDES_EVERY_RECEIPT_AND_MANIFEST",
        "RESULTING_DEPENDENCY_DAG_IS_QUALIFIED_ACYCLIC_AND_WITHIN_EVERY_REACHABLE_TERMINAL_CASCADE_BOUND",
    }
    expected_sidecar_names = {
        "AuthorityTransactionInstalledStateRoot",
        "AuthorityTransactionCommitReceipt",
        "SimulationSessionStateCommitReceipt",
        "SimulationSessionSubresourceCommitReceipt",
        "AuthorityTransactionPersistenceManifest",
        "SimulationSessionSubresourcePersistenceManifest",
    }
    terminal_cascade_ref = (
        "simulation-session-subresource-terminal-cascade-type::"
        "SimulationSessionSubresourceTerminalCascade"
    )
    for event_id in expected_subresource_events:
        event = events[(selector_id, event_id)]
        label = f"{selector_id}.{event_id}"
        domain = subresource_domain_by_event[event_id]
        require_exact(
            event["transition_kind_state_domain"],
            domain,
            f"{label}: transition domain",
        )
        bindings = set(event["pre_cas_content"]["required_bindings"])
        require(
            common_bindings.issubset(bindings),
            f"{label}: common subresource invariants are incomplete",
        )
        sidecar_names = {
            item["artifact"].split("::", 1)[1] for item in event["post_cas_sidecars"]
        }
        require_exact(
            sidecar_names,
            expected_sidecar_names,
            f"{label}: receipt and persistence surface",
        )
        if event_id in terminal_events:
            require_exact(
                event["operation_scope"],
                "BOUNDED_KEY_SET",
                f"{label}: terminal cascade scope",
            )
            require_exact(
                event_edges(event, "ROOT"),
                {
                    ("ACTIVE", "ACTIVE"),
                    ("RETIRED_DRAIN_ONLY", "RETIRED_DRAIN_ONLY"),
                },
                f"{label}: active/drain-only root paths",
            )
            require(
                {
                    "EXACT_TERMINAL_CASCADE_DERIVED_WITHOUT_CALLER_SELECTED_CAUSE",
                    "MISSING_EXTRA_DUPLICATE_TERMINAL_UNRELATED_OR_WRONG_ORDER_CASCADE_MEMBER_REJECTS_BEFORE_CAS",
                    "EVERY_CANONICAL_TERMINAL_CASCADE_ENTRY_BINDS_RESOURCE_CLASS_KEY_EXACT_PRIOR_MEMBER_BYTES_STATE_DEPENDENCY_SET_DERIVED_CAUSE_AND_RECEIPT_FREE_INSTALLED_TOMBSTONE",
                }.issubset(bindings),
                f"{label}: terminal-cascade guards are incomplete",
            )
            cascade_consumes = [
                item
                for item in event["consumes"]
                if item["artifact"] == terminal_cascade_ref
                and item["role"] == "EXACT_RECEIPT_FREE_TERMINAL_CASCADE"
            ]
            require_exact(
                len(cascade_consumes),
                1,
                f"{label}: terminal-cascade input",
            )
            require_exact(
                {partition["state_domain"] for partition in event["partition_effects"]},
                set(registry_domains),
                f"{label}: cascade partition domains",
            )
            for partition in event["partition_effects"]:
                require_exact(
                    partition["inventory_semantics"],
                    (
                        "INITIATING_MEMBER_PLUS_COMPLETE_TRANSITIVE_"
                        "NONTERMINAL_DEPENDENT_CLOSURE"
                    ),
                    f"{label}.{partition['partition_id']}: cascade inventory",
                )
                require(
                    all(
                        branch["to_state"] == "TERMINAL"
                        for branch in partition["branches"]
                    ),
                    f"{label}.{partition['partition_id']}: nonterminal cascade result",
                )
        else:
            require_exact(
                event["operation_scope"],
                "EXACT_ONE_KEY",
                f"{label}: nonterminal operation scope",
            )
            require_exact(
                event_edges(event, "ROOT"),
                {("ACTIVE", "ACTIVE")},
                f"{label}: active-only root path",
            )
            require(
                "TYPED_EMPTY_TERMINAL_CASCADE" in bindings,
                f"{label}: nonterminal operation lacks an empty cascade",
            )

    retire = events[(selector_id, "RETIRE_SIMULATION_SESSION_GENERATION")]
    finalize = events[(selector_id, "FINALIZE_SIMULATION_SESSION_GENERATION")]
    require_exact(
        {partition["state_domain"] for partition in retire["partition_effects"]},
        set(registry_domains),
        "simulation retirement registry partition",
    )
    for partition in retire["partition_effects"]:
        domain_states = set(domains[(selector_id, partition["state_domain"])]["states"])
        require_exact(
            partition["inventory_semantics"],
            "EXACT_COMPLETE_BOUNDED_CANONICAL_FROZEN_MEMBER_PARTITION",
            f"simulation retirement {partition['state_domain']}: inventory",
        )
        require_exact(
            {
                (branch["from_state"], branch["to_state"])
                for branch in partition["branches"]
            },
            {(state, state) for state in domain_states},
            f"simulation retirement {partition['state_domain']}: frozen states",
        )
    require(
        {
            "RETIREMENT_DOES_NOT_SILENTLY_TERMINALIZE_A_SUBRESOURCE",
            "RETIREMENT_PARTITION_FREEZES_EVERY_PRIOR_MEMBER_STATE_DEPENDENCY_SET_AND_OPERATION_RESULT_LOCATOR",
        }.issubset(retire["pre_cas_content"]["required_bindings"]),
        "simulation retirement freeze contract is incomplete",
    )
    require_exact(
        {partition["state_domain"] for partition in finalize["partition_effects"]},
        set(registry_domains),
        "simulation finalization registry partition",
    )
    for partition in finalize["partition_effects"]:
        require_exact(
            {
                (branch["from_state"], branch["to_state"])
                for branch in partition["branches"]
            },
            {("ABSENT", "ABSENT"), ("TERMINAL", "TERMINAL")},
            f"simulation finalization {partition['state_domain']}: terminal closure",
        )
    require(
        {
            "EVERY_INDEXED_OPERATION_HAS_ITS_EXACT_RETAINED_RESULT",
            "EVERY_OPERATION_JOB_OUTPUT_STREAM_RESOURCE_GRANT_DELIVERY_AND_OBSERVER_OBLIGATION_IS_TERMINAL",
        }.issubset(finalize["pre_cas_content"]["required_bindings"]),
        "simulation finalization terminal proof is incomplete",
    )


def _run_selector_extension_contract_self_test(data: dict[str, Any]) -> int:
    artifacts = set(data["artifacts"])

    def validate_handoff(candidate: dict[str, Any]) -> None:
        _validate_handoff_quiescence_bijections(candidate, set(candidate["artifacts"]))

    def validate_simulation(candidate: dict[str, Any]) -> None:
        candidate_selectors, candidate_events, candidate_domains = _selector_indexes(
            candidate
        )
        _validate_simulation_subresource_architecture(
            candidate,
            candidate_selectors,
            candidate_events,
            candidate_domains,
            set(candidate["artifacts"]),
        )

    def validate_anchor(candidate: dict[str, Any]) -> None:
        candidate_selectors, candidate_events, candidate_domains = _selector_indexes(
            candidate
        )
        _validate_independent_anchor_architecture(
            candidate,
            candidate_selectors,
            candidate_events,
            candidate_domains,
        )

    _validate_handoff_quiescence_bijections(data, artifacts)
    validate_simulation(data)
    validate_anchor(data)
    mutations: list[tuple[str, Any, Any]] = []

    def mutate_handoff_rule(candidate: dict[str, Any]) -> None:
        observer = next(
            selector
            for selector in candidate["selectors"]
            if selector["selector_id"] == "OBSERVER_AUTHORIZATION"
        )
        partition = next(
            partition
            for event in observer["events"]
            for partition in event["partition_effects"]
            if "handoff_quiescence_bijection" in partition
        )
        partition["handoff_quiescence_bijection"]["rule"] = "ALLOW_UNPROVED_HANDOFF"

    mutations.append(("permissive handoff rule", mutate_handoff_rule, validate_handoff))

    def mutate_simulation_cascade_order(candidate: dict[str, Any]) -> None:
        candidate["simulation_session_state_profile"]["subresource_dependency_dag"][
            "terminal_cascade"
        ] = "CALLER_ORDER"

    mutations.append(
        (
            "caller-selected simulation cascade order",
            mutate_simulation_cascade_order,
            validate_simulation,
        )
    )

    def mutate_simulation_cause(candidate: dict[str, Any]) -> None:
        candidate["simulation_session_state_profile"]["terminal_cause_policy"][
            "dependent_cause_by_resource_class"
        ]["OUTPUT_STREAM"] = "JOB_COMPLETED"

    mutations.append(
        (
            "cross-class simulation terminal cause",
            mutate_simulation_cause,
            validate_simulation,
        )
    )

    def mutate_simulation_partition(candidate: dict[str, Any]) -> None:
        event = next(
            event
            for selector in candidate["selectors"]
            if selector["selector_id"] == "SIMULATION_SESSION_STATE"
            for event in selector["events"]
            if event["event_id"] == "TERMINALIZE_SIMULATION_JOB"
        )
        event["partition_effects"].pop()

    mutations.append(
        (
            "incomplete simulation terminal cascade partition",
            mutate_simulation_partition,
            validate_simulation,
        )
    )

    def mutate_simulation_scope(candidate: dict[str, Any]) -> None:
        event = next(
            event
            for selector in candidate["selectors"]
            if selector["selector_id"] == "SIMULATION_SESSION_STATE"
            for event in selector["events"]
            if event["event_id"] == "RECORD_SIMULATION_JOB_PROGRESS"
        )
        event["operation_scope"] = "BOUNDED_KEY_SET"

    mutations.append(
        (
            "widened simulation progress scope",
            mutate_simulation_scope,
            validate_simulation,
        )
    )

    def mutate_anchor_capacity_refund(candidate: dict[str, Any]) -> None:
        event = next(
            event
            for selector in candidate["selectors"]
            if selector["selector_id"]
            == "INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_REGISTRY"
            for event in selector["events"]
            if event["event_id"]
            == "RESERVE_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR_NAMESPACE_CAPACITY"
        )
        event["pre_cas_content"]["required_bindings"].remove(
            "TERMINAL_ABANDONED_OR_MATERIALIZED_RESERVATIONS_NEVER_REFUND_"
            "REASSIGN_OR_TIME_RELEASE_THE_CHARGE"
        )

    mutations.append(
        (
            "refundable independent-anchor reservation",
            mutate_anchor_capacity_refund,
            validate_anchor,
        )
    )

    def mutate_anchor_joint_participant(candidate: dict[str, Any]) -> None:
        profile = candidate["joint_selector_transaction_profiles"][
            "JTX_ANCHOR_GENESIS_FROM_RESERVED_NAMESPACE_CAPACITY"
        ]
        profile["participants"].pop()
        profile["declared_writing_participant_count"] = 1

    mutations.append(
        (
            "partial anchor genesis transaction",
            mutate_anchor_joint_participant,
            validate_anchor,
        )
    )

    killed = 0
    for label, mutate, validate in mutations:
        hostile = copy.deepcopy(data)
        mutate(hostile)
        try:
            validate(hostile)
        except ClosureCheckError:
            killed += 1
        else:
            fail(f"selector extension self-test survived: {label}")
    return killed


def _validate_independent_anchor_architecture(
    data: dict[str, Any],
    selectors: dict[str, dict[str, Any]],
    events: dict[tuple[str, str], dict[str, Any]],
    domains: dict[tuple[str, str], dict[str, Any]],
) -> None:
    registry_id = "INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_REGISTRY"
    anchor_id = "OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR"
    registry = selectors[registry_id]
    anchor = selectors[anchor_id]
    require_exact(
        registry["owner"],
        "independent-anchor-authority",
        "anchor reservation registry owner",
    )
    require_exact(
        anchor["owner"],
        "independent-exposure-anchor",
        "challenge exposure anchor owner",
    )
    require_exact(
        registry["selector"],
        (
            "installed-independent-anchor-namespace-reservation-registry-"
            "selector-identity::"
            "InstalledIndependentAnchorNamespaceReservationRegistrySelector"
        ),
        "anchor reservation registry selector",
    )
    require_exact(
        anchor["selector"],
        (
            "installed-observer-grant-challenge-exposure-anchor-selector-"
            "identity::InstalledObserverGrantChallengeExposureAnchorSelector"
        ),
        "challenge exposure anchor selector",
    )

    registry_domain_names = {
        domain["state_domain"] for domain in registry["state_domains"]
    }
    require_exact(
        registry_domain_names,
        {
            "ROOT",
            "NAMESPACE_RESERVATION_ENTRY",
            "SOURCE_NAMESPACE_ALIAS_INDEX_ENTRY",
            "LINEAGE_INCARNATION_ALIAS_INDEX_ENTRY",
            "SOURCE_INDEX_INCARNATION_ALIAS_INDEX_ENTRY",
            "ANCHOR_SELECTOR_INCARNATION_ALIAS_INDEX_ENTRY",
        },
        "anchor reservation registry domains",
    )
    reservation = domains[(registry_id, "NAMESPACE_RESERVATION_ENTRY")]
    require_exact(
        reservation["key_coordinates"],
        ["ANCHOR_AUTHORITY_KEY", "SOURCE_OWNER_KEY", "SOURCE_OWNER_LIFETIME_SLOT"],
        "anchor reservation stable key",
    )
    require_exact(
        reservation["states"],
        [
            "ABSENT",
            "MATERIALIZED",
            "RESERVED_PENDING_ANCHOR_GENESIS",
            "TERMINAL_RETAINED",
        ],
        "anchor reservation states",
    )
    require_exact(
        domains[(registry_id, "ROOT")]["terminality"],
        "PERSISTENT_HIGHER_AUTHORITY_REGISTRY",
        "anchor reservation registry lifetime",
    )
    alias_coordinates = {
        "SOURCE_NAMESPACE_ALIAS_INDEX_ENTRY": "SOURCE_NAMESPACE_KEY",
        "LINEAGE_INCARNATION_ALIAS_INDEX_ENTRY": ("PREALLOCATED_LINEAGE_INCARNATION"),
        "SOURCE_INDEX_INCARNATION_ALIAS_INDEX_ENTRY": (
            "PREALLOCATED_SOURCE_INDEX_INCARNATION"
        ),
        "ANCHOR_SELECTOR_INCARNATION_ALIAS_INDEX_ENTRY": (
            "PREALLOCATED_ANCHOR_SELECTOR_INCARNATION"
        ),
    }
    for domain_name, coordinate in alias_coordinates.items():
        alias = domains[(registry_id, domain_name)]
        require_exact(
            alias["key_coordinates"],
            ["ANCHOR_AUTHORITY_KEY", coordinate],
            f"{registry_id}.{domain_name}: key",
        )
        require_exact(
            alias["states"],
            ["ABSENT", "RETAINED_BINDING"],
            f"{registry_id}.{domain_name}: retained binding states",
        )

    def event_edges(
        selector_id: str,
        event_id: str,
        state_domain: str,
    ) -> set[tuple[str, str]]:
        selector = selectors[selector_id]
        edge_by_id = {edge["edge_id"]: edge for edge in selector["state_edge_catalog"]}
        return {
            (edge_by_id[edge_ref]["from_state"], edge_by_id[edge_ref]["to_state"])
            for case in events[(selector_id, event_id)]["transition_cases"]
            for edge_ref in case["state_edge_refs"]
            if edge_by_id[edge_ref]["state_domain"] == state_domain
        }

    reserve_event = (
        "RESERVE_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR_NAMESPACE_CAPACITY"
    )
    require_exact(
        event_edges(registry_id, reserve_event, "NAMESPACE_RESERVATION_ENTRY"),
        {("ABSENT", "RESERVED_PENDING_ANCHOR_GENESIS")},
        "anchor namespace capacity reservation edge",
    )
    for domain_name in alias_coordinates:
        require_exact(
            event_edges(registry_id, reserve_event, domain_name),
            {("ABSENT", "RETAINED_BINDING")},
            f"anchor reservation {domain_name}: never-reuse installation",
        )
    reserve_bindings = set(
        events[(registry_id, reserve_event)]["pre_cas_content"]["required_bindings"]
    )
    require(
        {
            "EXACT_RESERVATION_KEY_IS_ONLY_ANCHOR_AUTHORITY_KEY_SOURCE_OWNER_KEY_AND_SOURCE_OWNER_LIFETIME_SLOT",
            "GLOBAL_USED_PLUS_REMAINING_EQUALS_MANIFEST_FIXED_TOTAL_WITHOUT_OVERFLOW_UNDERFLOW_OR_BORROW",
            "INSTALLED_GLOBAL_COUNT_AND_BYTES_DO_NOT_EXCEED_MANIFEST_FIXED_CAPS",
            "INSTALLED_SOURCE_OWNER_COUNT_AND_BYTES_DO_NOT_EXCEED_EXACT_PREALLOCATED_QUOTA",
            "NONBORROWABLE_DOMAIN_RETIREMENT_RESERVE_REMAINS_FULLY_AVAILABLE_AFTER_THE_CHARGE",
            "SAME_CAS_INSTALLS_NEVER_REUSED_NAMESPACE_LINEAGE_SOURCE_INDEX_AND_ANCHOR_SELECTOR_ALIAS_INDEXES",
            "TERMINAL_ABANDONED_OR_MATERIALIZED_RESERVATIONS_NEVER_REFUND_REASSIGN_OR_TIME_RELEASE_THE_CHARGE",
            "UNKNOWN_DEFAULT_ALIAS_REKEY_REUSE_TIMEOUT_RECLAMATION_OR_CAPACITY_OVERCOMMIT_REJECTS",
        }.issubset(reserve_bindings),
        "anchor namespace capacity and never-reuse contract is incomplete",
    )

    create_event = "CREATE_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR"
    require_exact(
        event_edges(registry_id, create_event, "NAMESPACE_RESERVATION_ENTRY"),
        {("RESERVED_PENDING_ANCHOR_GENESIS", "MATERIALIZED")},
        "anchor reservation materialization edge",
    )
    registry_terminal_events = {
        (
            "FINALIZE_INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_AFTER_"
            "SOURCE_INTENT_CANCELLATION"
        ): {
            ("ABSENT", "TERMINAL_RETAINED"),
            ("RESERVED_PENDING_ANCHOR_GENESIS", "TERMINAL_RETAINED"),
        },
        (
            "FINALIZE_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR_AFTER_"
            "COOPERATIVE_SOURCE_RETIREMENT"
        ): {("MATERIALIZED", "TERMINAL_RETAINED")},
        (
            "FINALIZE_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR_AFTER_"
            "PERMANENT_SOURCE_ISOLATION"
        ): {("MATERIALIZED", "TERMINAL_RETAINED")},
        (
            "FINALIZE_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR_AFTER_"
            "SOURCE_NAMESPACE_CANCELLATION"
        ): {
            ("MATERIALIZED", "TERMINAL_RETAINED"),
            ("RESERVED_PENDING_ANCHOR_GENESIS", "TERMINAL_RETAINED"),
        },
    }
    for event_id, expected_edges in registry_terminal_events.items():
        require_exact(
            event_edges(registry_id, event_id, "NAMESPACE_RESERVATION_ENTRY"),
            expected_edges,
            f"{registry_id}.{event_id}: retained terminalization",
        )

    anchor_domain_names = {domain["state_domain"] for domain in anchor["state_domains"]}
    require_exact(
        anchor_domain_names,
        {
            "ROOT",
            "ELIGIBLE_OBSERVER_ROOT_ENTRY",
            "CHALLENGE_EXPOSURE_ENTRY",
            "CLOSURE_EVIDENCE_STATE",
        },
        "challenge exposure anchor domains",
    )
    anchor_root = domains[(anchor_id, "ROOT")]
    require_exact(
        anchor_root["states"],
        [
            "ABSENT_NEVER_USED",
            "ANCHOR_FROZEN_AFTER_TERMINAL_SOURCE_CLOSURE",
            "ANCHOR_OPEN",
            "ANCHOR_TERMINAL_AFTER_SOURCE_NAMESPACE_CANCELLATION",
        ],
        "challenge exposure anchor root states",
    )
    require_exact(
        set(anchor_root["terminal_states"]),
        {
            "ANCHOR_FROZEN_AFTER_TERMINAL_SOURCE_CLOSURE",
            "ANCHOR_TERMINAL_AFTER_SOURCE_NAMESPACE_CANCELLATION",
        },
        "challenge exposure anchor terminal states",
    )
    require_exact(
        domains[(anchor_id, "ELIGIBLE_OBSERVER_ROOT_ENTRY")]["states"],
        ["ABSENT", "ENROLLED"],
        "anchor observer-root enrollment states",
    )
    require_exact(
        domains[(anchor_id, "CHALLENGE_EXPOSURE_ENTRY")]["states"],
        ["ABSENT", "APPENDED"],
        "anchor append-only challenge states",
    )
    require_exact(
        domains[(anchor_id, "CLOSURE_EVIDENCE_STATE")]["states"],
        [
            "COOPERATIVE_AND_ISOLATION",
            "COOPERATIVE_ONLY",
            "ISOLATION_ONLY",
            "NOT_APPLICABLE_OPEN",
        ],
        "anchor closure-evidence states",
    )
    require_exact(
        event_edges(anchor_id, create_event, "ROOT"),
        {("ABSENT_NEVER_USED", "ANCHOR_OPEN")},
        "challenge exposure anchor genesis edge",
    )
    require_exact(
        event_edges(
            anchor_id,
            "ENROLL_OBSERVER_ROOT_IN_CHALLENGE_EXPOSURE_ANCHOR",
            "ELIGIBLE_OBSERVER_ROOT_ENTRY",
        ),
        {("ABSENT", "ENROLLED")},
        "challenge exposure anchor root-enrollment edge",
    )
    require_exact(
        event_edges(
            anchor_id,
            "ANCHOR_OBSERVER_GRANT_CHALLENGE_BEFORE_EXPOSURE",
            "CHALLENGE_EXPOSURE_ENTRY",
        ),
        {("ABSENT", "APPENDED")},
        "challenge exposure anchor append edge",
    )

    append_bindings = set(
        events[(anchor_id, "ANCHOR_OBSERVER_GRANT_CHALLENGE_BEFORE_EXPOSURE")][
            "pre_cas_content"
        ]["required_bindings"]
    )
    require(
        {
            "BOTH_DISJOINT_AUDIENCE_FAMILIES_SOURCE_AUDIENCE_CAPSULE_RETENTION_AND_EXACT_RETRY_DURABLE_BEFORE_ADMISSION",
            "COMPLETE_SOURCE_CHALLENGE_APPEND_RECEIPT_PROJECTION_ENVELOPE_MANIFEST_PREMANIFEST_COMPLETION_CAPSULE_AND_PASSING_VERIFICATION_MATCH_EXACTLY",
            "FINAL_OBSERVER_CAPSULES_ARE_CONSTRUCTED_ONLY_AFTER_SHARED_COMPLETION_AND_ARE_NOT_INPUTS_TO_THE_SOURCE_ENVELOPE",
        }.issubset(append_bindings),
        "anchor append producer/audience ordering is incomplete",
    )
    enroll_bindings = set(
        events[(anchor_id, "ENROLL_OBSERVER_ROOT_IN_CHALLENGE_EXPOSURE_ANCHOR")][
            "pre_cas_content"
        ]["required_bindings"]
    )
    require(
        {
            "ANCHOR_ENTRY_ALONE_GRANTS_NO_SOURCE_PREPARE_CHALLENGE_ISSUANCE_OR_CLOSURE_AUDIENCE",
            "COMPLETE_PROTECTED_SOURCE_PENDING_ELIGIBILITY_HIERARCHY_IS_THE_ONLY_ANCHOR_AUTHORITY_INPUT",
            "PENDING_ELIGIBILITY_ANCHOR_ENROLLMENT_AND_SOURCE_CONFIRMATION_BIND_THE_SAME_RELATION_DIGEST_AND_CAPTURED_CUTOFF",
        }.issubset(enroll_bindings),
        "anchor observer-root enrollment hierarchy is incomplete",
    )

    cooperative_event = (
        "FINALIZE_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR_AFTER_"
        "COOPERATIVE_SOURCE_RETIREMENT"
    )
    isolation_event = (
        "FINALIZE_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR_AFTER_"
        "PERMANENT_SOURCE_ISOLATION"
    )
    for event_id, evidence_edge, required_binding in (
        (
            cooperative_event,
            ("NOT_APPLICABLE_OPEN", "COOPERATIVE_ONLY"),
            (
                "COMPLETE_PROTECTED_COOPERATIVE_RETIREMENT_HIERARCHY_BINDS_"
                "RETIRED_NAMESPACE_LINEAGE_FROZEN_SOURCE_INDEX_ACCEPTED_GRANT_"
                "CLOSURE_NO_SUCCESSOR_AND_RETIREMENT_RECEIPT"
            ),
        ),
        (
            isolation_event,
            ("NOT_APPLICABLE_OPEN", "ISOLATION_ONLY"),
            (
                "EVERY_CREDENTIAL_STORE_SELECTOR_REPLICA_CACHE_OUTBOX_QUEUE_"
                "INFLIGHT_RECOVERY_SUCCESSOR_DERIVED_CONSUMER_AND_PHYSICAL_"
                "AUTHORITY_SURFACE_CLOSED"
            ),
        ),
    ):
        require_exact(
            event_edges(anchor_id, event_id, "ROOT"),
            {("ANCHOR_OPEN", "ANCHOR_FROZEN_AFTER_TERMINAL_SOURCE_CLOSURE")},
            f"{anchor_id}.{event_id}: frozen root",
        )
        require_exact(
            event_edges(anchor_id, event_id, "CLOSURE_EVIDENCE_STATE"),
            {evidence_edge},
            f"{anchor_id}.{event_id}: closure evidence",
        )
        require(
            required_binding
            in events[(anchor_id, event_id)]["pre_cas_content"]["required_bindings"],
            f"{anchor_id}.{event_id}: protected closure evidence is incomplete",
        )
    require_exact(
        event_edges(
            anchor_id,
            "REFINE_FROZEN_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR_WITH_"
            "MISSING_SOURCE_CLOSURE_EVIDENCE",
            "CLOSURE_EVIDENCE_STATE",
        ),
        {
            ("COOPERATIVE_ONLY", "COOPERATIVE_AND_ISOLATION"),
            ("ISOLATION_ONLY", "COOPERATIVE_AND_ISOLATION"),
        },
        "anchor monotonic closure-evidence refinement",
    )

    expected_joint_profiles = {
        "JTX_ANCHOR_GENESIS_FROM_RESERVED_NAMESPACE_CAPACITY": create_event,
        "JTX_ANCHOR_COOPERATIVE_SOURCE_RETIREMENT_FINALIZATION": cooperative_event,
        "JTX_ANCHOR_PERMANENT_SOURCE_ISOLATION_FINALIZATION": isolation_event,
        "JTX_ANCHOR_SOURCE_NAMESPACE_CANCELLATION_FINALIZATION": (
            "FINALIZE_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR_AFTER_"
            "SOURCE_NAMESPACE_CANCELLATION"
        ),
    }
    for profile_id, event_id in expected_joint_profiles.items():
        profile = data["joint_selector_transaction_profiles"][profile_id]
        require_exact(
            {
                (participant["selector_id"], participant["event_id"])
                for participant in profile["participants"]
            },
            {(registry_id, event_id), (anchor_id, event_id)},
            f"{profile_id}: anchor/reservation participants",
        )
        require_exact(
            profile["declared_writing_participant_count"],
            2,
            f"{profile_id}: writer count",
        )


def _require_binding(
    events: dict[tuple[str, str], dict[str, Any]],
    key: tuple[str, str],
    binding: str,
) -> None:
    require(key in events, f"missing critical event {key}")
    require(
        binding in events[key]["pre_cas_content"]["required_bindings"],
        f"{key}: missing critical binding {binding}",
    )


def _validate_case_variant_write_role_closure(
    *,
    label: str,
    contract: dict[str, Any],
) -> None:
    """Close case-specific writes against the contract's participant variants."""

    case_write_roles = contract.get("write_roles_by_semantic_case")
    if case_write_roles is None:
        return
    variants = contract["participant_role_variants"]
    if len(variants) == 1:
        require_exact(
            set(variants[0]["write_roles"]),
            set(contract["write_roles"]),
            f"{label}: single-variant write-role union",
        )
        return
    require_exact(
        sorted(tuple(sorted(variant["write_roles"])) for variant in variants),
        sorted(tuple(sorted(roles)) for roles in case_write_roles.values()),
        f"{label}: case/variant write-role multiset closure",
    )


def _run_case_variant_write_role_closure_self_test() -> int:
    contract = {
        "participant_role_variants": [
            {"write_roles": ["DOMAIN_STATE", "PRIMARY", "SECONDARY"]},
            {"write_roles": ["DOMAIN_STATE", "PRIMARY"]},
            {"write_roles": ["DOMAIN_STATE", "PRIMARY"]},
        ],
        "write_roles": ["DOMAIN_STATE", "PRIMARY", "SECONDARY"],
        "write_roles_by_semantic_case": {
            "ACTIVE": ["DOMAIN_STATE", "PRIMARY", "SECONDARY"],
            "PENDING_PARTIAL": ["DOMAIN_STATE", "PRIMARY"],
            "PENDING_CONFIRMED": ["DOMAIN_STATE", "PRIMARY"],
        },
    }
    _validate_case_variant_write_role_closure(
        label="synthetic multi-variant contract",
        contract=contract,
    )
    killed = 0
    for label, mutate in (
        (
            "missing narrowed variant",
            lambda candidate: candidate["participant_role_variants"].__setitem__(
                2,
                {"write_roles": ["DOMAIN_STATE", "PRIMARY", "SECONDARY"]},
            ),
        ),
        (
            "extra narrowed case",
            lambda candidate: candidate["write_roles_by_semantic_case"].__setitem__(
                "ACTIVE",
                ["DOMAIN_STATE", "PRIMARY"],
            ),
        ),
    ):
        hostile = copy.deepcopy(contract)
        mutate(hostile)
        try:
            _validate_case_variant_write_role_closure(
                label=f"synthetic {label}",
                contract=hostile,
            )
        except ClosureCheckError:
            killed += 1
        else:
            fail(f"case/variant write-role self-test accepted {label}")
    single_variant = {
        "participant_role_variants": [
            {"write_roles": ["DOMAIN_STATE", "PRIMARY", "SECONDARY"]}
        ],
        "write_roles": ["DOMAIN_STATE", "PRIMARY", "SECONDARY"],
        "write_roles_by_semantic_case": {
            "ABSENT": ["DOMAIN_STATE", "PRIMARY", "SECONDARY"],
            "PRESENT": ["DOMAIN_STATE", "PRIMARY"],
        },
    }
    _validate_case_variant_write_role_closure(
        label="synthetic single-variant contract",
        contract=single_variant,
    )
    single_variant["participant_role_variants"][0]["write_roles"].pop()
    try:
        _validate_case_variant_write_role_closure(
            label="synthetic narrowed single variant",
            contract=single_variant,
        )
    except ClosureCheckError:
        killed += 1
    else:
        fail("case/variant write-role self-test accepted a narrowed single variant")
    return killed


def _validate_authority_transaction_architecture(
    data: dict[str, Any],
) -> None:
    selectors, events, domains = _selector_indexes(data)

    authority_selector_roles = {
        "AUTHORITY_TRANSACTION_DOMAIN": "AUTHORITY_TRANSACTION_DOMAIN_STATE",
        "LOGICAL_SESSION_NAMESPACE_REGISTRY": ("LOGICAL_SESSION_NAMESPACE_REGISTRY"),
        "LOGICAL_SESSION_GENERATION_LINEAGE": "LOGICAL_SESSION_LINEAGE",
        "SIMULATION_SESSION_STATE": "SIMULATION_SESSION_STATE",
        "BODY_SESSION_CONTROL": "BODY_SESSION_CONTROL",
        "OBSERVER_AUTHORIZATION": "OBSERVER_AUTHORIZATION",
        "OBSERVER_ATTACHMENT_TARGET_HISTORY": "OBSERVER_TARGET_HISTORY",
        "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX": (
            "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX"
        ),
        "OBSERVER_UNRESOLVED_TARGET_QUARANTINE": (
            "OBSERVER_UNRESOLVED_TARGET_QUARANTINE"
        ),
        "INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_REGISTRY": (
            "INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_REGISTRY"
        ),
        "OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR": (
            "OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR"
        ),
        "ACTUATION_AUTHORITY_DOMAIN": ("ACTUATION_DOMAIN_REGISTRY_AND_ARBITER"),
        "SECURITY_AUTHORITY": "LOCAL_SECURITY_ENFORCEMENT",
    }
    closed_roles = {
        "AUTHORITY_TRANSACTION_DOMAIN_STATE",
        "LOGICAL_SESSION_NAMESPACE_REGISTRY",
        "LOGICAL_SESSION_LINEAGE",
        "SIMULATION_SESSION_STATE",
        "BODY_SESSION_CONTROL",
        "OBSERVER_AUTHORIZATION",
        "OBSERVER_TARGET_HISTORY",
        "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX",
        "OBSERVER_UNRESOLVED_TARGET_QUARANTINE",
        "ACTUATION_DOMAIN_REGISTRY_AND_ARBITER",
        "LOCAL_SECURITY_ENFORCEMENT",
    }
    independent_anchor_closed_roles = {
        "AUTHORITY_TRANSACTION_DOMAIN_STATE",
        "INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_REGISTRY",
        "OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR",
        "LOCAL_SECURITY_ENFORCEMENT",
    }
    independent_anchor_selectors = {
        "INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_REGISTRY",
        "OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR",
    }
    restricted_role_universe_by_event = {
        (
            "INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_REGISTRY",
            "FINALIZE_INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_AFTER_"
            "SOURCE_INTENT_CANCELLATION",
        ): {
            "AUTHORITY_TRANSACTION_DOMAIN_STATE",
            "INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_REGISTRY",
            "LOCAL_SECURITY_ENFORCEMENT",
        },
        (
            "OBSERVER_AUTHORIZATION",
            "ACTIVATE_OBSERVER_AUTHORIZATION_AFTER_PARENT_CONFIRMATION",
        ): {
            "AUTHORITY_TRANSACTION_DOMAIN_STATE",
            "LOGICAL_SESSION_LINEAGE",
            "LOCAL_SECURITY_ENFORCEMENT",
            "OBSERVER_AUTHORIZATION",
        },
    }
    simulation_subresource_roles = {
        "AUTHORITY_TRANSACTION_DOMAIN_STATE",
        "LOCAL_SECURITY_ENFORCEMENT",
        "LOGICAL_SESSION_LINEAGE",
        "SIMULATION_SESSION_STATE",
    }
    restricted_role_universe_by_event.update(
        {
            ("SIMULATION_SESSION_STATE", event_id): simulation_subresource_roles
            for event_id in data["simulation_session_state_profile"][
                "subresource_event_kinds"
            ]
        }
    )
    plant_roles = {
        "AUTHORITY_TRANSACTION_DOMAIN_STATE",
        "LOGICAL_SESSION_LINEAGE",
        "BODY_SESSION_CONTROL",
        "OBSERVER_AUTHORIZATION",
        "ACTUATION_DOMAIN_REGISTRY_AND_ARBITER",
        "LOCAL_SECURITY_ENFORCEMENT",
    }
    source_retirement_roles = {
        "AUTHORITY_TRANSACTION_DOMAIN_STATE",
        "LOGICAL_SESSION_NAMESPACE_REGISTRY",
        "LOGICAL_SESSION_LINEAGE",
        "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX",
        "OBSERVER_TARGET_HISTORY",
        "OBSERVER_UNRESOLVED_TARGET_QUARANTINE",
    }
    source_lineage_write_roles = {
        "AUTHORITY_TRANSACTION_DOMAIN_STATE",
        "LOGICAL_SESSION_NAMESPACE_REGISTRY",
        "LOGICAL_SESSION_LINEAGE",
        "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX",
    }
    for key in (
        (
            "LOGICAL_SESSION_GENERATION_LINEAGE",
            "LOGICAL_SESSION_GENERATION_LINEAGE_GENESIS_FROM_SERVER_AUTHORITY",
        ),
        (
            "LOGICAL_SESSION_NAMESPACE_REGISTRY",
            "REGISTER_SOURCE_LOGICAL_SESSION_LINEAGE",
        ),
        (
            "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX",
            (
                "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX_GENESIS_"
                "FROM_SOURCE_LINEAGE_REGISTRATION"
            ),
        ),
    ):
        require(key in events, f"missing source-lineage transaction {key}")
        contract = events[key].get("authority_transaction_contract")
        require(
            isinstance(contract, dict),
            f"{key}: missing source-lineage authority transaction",
        )
        require_exact(
            set(contract["write_roles"]),
            source_lineage_write_roles,
            f"{key}: source-lineage write roles",
        )
        for variant in contract["participant_role_variants"]:
            require_exact(
                set(variant["write_roles"]),
                source_lineage_write_roles,
                f"{key}: source-lineage variant write roles",
            )
            require(
                "LOCAL_SECURITY_ENFORCEMENT" in variant["participant_roles"]
                and "LOCAL_SECURITY_ENFORCEMENT" not in variant["write_roles"],
                (
                    f"{key}: local security must remain a read participant, "
                    "not a source-lineage writer"
                ),
            )
    installed_root = (
        "authority-transaction-installed-state-root-type::"
        "AuthorityTransactionInstalledStateRoot"
    )
    transaction_receipt = (
        "authority-transaction-commit-receipt-type::AuthorityTransactionCommitReceipt"
    )
    persistence_manifest = (
        "authority-transaction-persistence-manifest-type::"
        "AuthorityTransactionPersistenceManifest"
    )
    cas_condition = (
        "authority-transaction-cas-condition-type::AuthorityTransactionCASCondition"
    )
    qualification_receipt = (
        "authority-transaction-domain-qualification-receipt-type::"
        "AuthorityTransactionDomainQualificationReceipt"
    )
    participant_set = (
        "authority-transaction-domain-participant-set-type::"
        "AuthorityTransactionDomainParticipantSet"
    )
    role_policy_and_bounds = (
        "authority-transaction-domain-participant-role-policy-and-bounds-"
        "type::AuthorityTransactionDomainParticipantRolePolicyAndBounds"
    )
    semantic_commitment = (
        "pre-cas-authority-semantic-commitment-type::PreCASAuthoritySemanticCommitment"
    )
    prior_installed_evidence = (
        "prior-installed-evidence-receipt-type::PriorInstalledEvidenceReceipt"
    )
    post_candidate_sidecar_type = (
        "post-candidate-installed-state-sidecar-type::"
        "PostCandidateInstalledStateSidecar"
    )
    local_security_projection = (
        "local-security-currentness-condition-projection-type::"
        "LocalSecurityCurrentnessConditionProjection"
    )
    native_genesis_receipt = (
        "native-participant-genesis-receipt-type::NativeParticipantGenesisReceipt"
    )
    participant_admission_receipt = (
        "authority-transaction-domain-participant-admission-receipt-type::"
        "AuthorityTransactionDomainParticipantAdmissionReceipt"
    )
    participant_admission_commitment = (
        "authority-transaction-domain-participant-admission-commitment-type::"
        "AuthorityTransactionDomainParticipantAdmissionCommitment"
    )
    native_identity_set = (
        "native-participant-read-write-selector-identity-set-type::"
        "NativeParticipantReadWriteSelectorIdentitySet"
    )

    def event_edges(
        key: tuple[str, str],
        state_domain: str,
    ) -> set[tuple[str, str]]:
        require(key in events, f"missing authority event {key}")
        catalog = {
            item["edge_id"]: item for item in selectors[key[0]]["state_edge_catalog"]
        }
        return {
            (state_edge["from_state"], state_edge["to_state"])
            for case in events[key]["transition_cases"]
            for state_edge in (
                case.get("state_edges")
                or [catalog[reference] for reference in case["state_edge_refs"]]
            )
            if state_edge["state_domain"] == state_domain
        }

    profile = data["authority_transaction_domain_profile"]
    require_exact(
        set(profile["closed_participant_roles"]),
        closed_roles,
        "authority transaction closed roles",
    )
    require_exact(
        set(profile["independent_anchor_closed_participant_roles"]),
        independent_anchor_closed_roles,
        "independent-anchor authority transaction closed roles",
    )
    require_exact(
        profile["candidate_repository_qualification_result"],
        "NOT_RUN",
        "authority transaction qualification status",
    )
    require_exact(
        profile["qualification"]["role_policy_and_bounds"],
        role_policy_and_bounds,
        "authority transaction static role policy",
    )
    require_exact(
        profile["qualification"]["dynamic_participant_set"],
        participant_set,
        "authority transaction dynamic participant set",
    )
    require_exact(
        set(profile["qualification"]["dynamic_entry_kinds"]),
        {
            "CURRENT_SELECTOR_PARTICIPANT",
            "LOST_REGISTERED_PARTICIPANT_EVIDENCE_ONLY",
        },
        "authority transaction dynamic participant entry kinds",
    )
    require(
        "PRE_READ" in profile["forbidden_atomicity_substitutes"]
        and "EVENTUAL_CONSISTENCY" in profile["forbidden_atomicity_substitutes"],
        "authority transaction profile permits a split currentness check",
    )
    projection_profile = profile["cas_condition"][
        "local_security_currentness_projection"
    ]
    require_exact(
        projection_profile["type"],
        local_security_projection,
        "local security currentness projection type",
    )
    require_exact(
        projection_profile["authority"],
        "NONAUTHORITATIVE",
        "local security currentness projection authority",
    )
    require_exact(
        projection_profile["independent_cas_or_currentness_root"],
        "FORBIDDEN",
        "local security projection independent-root rule",
    )
    require(
        "LocalSecurityCurrentnessCASCondition"
        not in json.dumps(data, ensure_ascii=False),
        "legacy local-security pseudo-CAS remains in selector source",
    )
    realm_binding_profile = data["realm_scoped_direct_binding_profile"]
    require_exact(
        realm_binding_profile["key_type"],
        "authority-realm-key-type::AuthorityRealmKey",
        "direct realm binding key type",
    )
    require_exact(
        set(realm_binding_profile["required_object_classes"]),
        {
            "AUTHORITY_REQUEST_AND_TRANSITION_FACT",
            "LEASE_AND_CURRENTNESS_COMMITMENT",
            "COMMAND_AND_COMMAND_FENCE",
            "EVIDENCE_AND_JOURNAL_RECORD",
            "RECEIPT_AND_PERSISTENCE_SIDECAR",
        },
        "direct realm binding object classes",
    )
    require(
        {
            "ROUTE_TEXT",
            "TRANSITIVE_DESCRIPTOR_OR_RECEIPT_ANCESTRY",
            "DEFAULT_OR_INFERRED_REALM",
        }.issubset(set(realm_binding_profile["forbidden_substitutes"])),
        "direct realm binding permits an inferred or transitive substitute",
    )
    forwarding_profile = data["forwarding_replay_profile"]
    require_exact(
        forwarding_profile["key_type"],
        "forwarding-replay-key-type::ForwardingReplayKey",
        "forwarding replay key type",
    )
    require_exact(
        forwarding_profile["stable_key_fields"],
        [
            "AUTHORITY_REALM_KEY",
            "SIGNER_PRINCIPAL",
            "SIGNED_OPERATION_OR_REPLAY_IDENTITY",
        ],
        "forwarding replay stable key",
    )
    require_exact(
        set(forwarding_profile["key_independent_of"]),
        {"CARRIER_IDENTITY", "CONTENT_OR_PAYLOAD_BYTES"},
        "forwarding replay carrier/content independence",
    )
    require_exact(
        set(forwarding_profile["conceptual_lookup_branches"]),
        {
            "FORWARDING_REPLAY_KEY_LOOKUP",
            "CONTENT_COMMITMENT_VALIDATED",
            "CONFLICT_REJECTED_NO_HANDOFF",
        },
        "forwarding replay conceptual closure",
    )
    require_exact(
        forwarding_profile["post_reservation_uncertainty"],
        "REMAINS_PENDING_UNTIL_QUERY_OR_TERMINAL_RESOLUTION",
        "forwarding replay uncertainty handling",
    )
    require(
        {
            "authority-realm-key-type::AuthorityRealmKey",
            "forwarding-replay-key-type::ForwardingReplayKey",
            "forwarding-replay-entry-type::ForwardingReplayEntry",
        }.issubset(data["artifacts"]),
        "realm or forwarding replay allocation is missing",
    )

    realm_selector_id = "AUTHORITY_REALM_ENROLLMENT_REGISTRY"
    realm_root = domains[(realm_selector_id, "ROOT")]
    require_exact(
        set(realm_root["states"]),
        {"ABSENT_NEVER_USED", "ACTIVE"},
        "higher authority registry root states",
    )
    require_exact(
        realm_root["absence_semantics"],
        "EXACT_SELECTOR_ABSENCE_WITH_NEVER_REUSE_TOMBSTONE",
        "higher authority registry selector absence",
    )
    require_exact(
        set(domains[(realm_selector_id, "COMMIT_POSITION_HIGH_WATER")]["states"]),
        {"ABSENT", "INSTALLED"},
        "higher authority registry commit-position states",
    )
    require_exact(
        set(domains[(realm_selector_id, "RETIREMENT_BUDGET")]["states"]),
        {"ABSENT", "RESERVED"},
        "higher authority registry retirement-budget states",
    )
    realm_qualification = (
        "authority-realm-enrollment-registry-qualification-type::"
        "AuthorityRealmEnrollmentRegistryQualification"
    )
    realm_qualification_receipt = (
        "authority-realm-enrollment-registry-qualification-receipt-type::"
        "AuthorityRealmEnrollmentRegistryQualificationReceipt"
    )
    realm_cas = (
        "authority-realm-enrollment-registry-cas-condition-type::"
        "AuthorityRealmEnrollmentRegistryCASCondition"
    )
    realm_commit = (
        "authority-realm-enrollment-registry-commit-receipt-type::"
        "AuthorityRealmEnrollmentRegistryCommitReceipt"
    )
    realm_manifest = (
        "authority-realm-enrollment-registry-persistence-manifest-type::"
        "AuthorityRealmEnrollmentRegistryPersistenceManifest"
    )
    realm_genesis_manifest = (
        "authority-realm-enrollment-registry-genesis-persistence-manifest-"
        "type::AuthorityRealmEnrollmentRegistryGenesisPersistenceManifest"
    )
    realm_budget = (
        "authority-realm-enrollment-registry-retirement-budget-type::"
        "AuthorityRealmEnrollmentRegistryRetirementBudget"
    )
    realm_profile = data["authority_realm_enrollment_registry_profile"]
    require_exact(
        realm_profile["qualification"],
        {
            "type": realm_qualification,
            "receipt": realm_qualification_receipt,
            "status": "NOT_RUN",
        },
        "higher authority registry qualification",
    )
    require_exact(
        realm_profile["transaction_contract"],
        {
            "cas_condition": realm_cas,
            "commit_receipt": realm_commit,
            "persistence_manifest": realm_manifest,
            "genesis_persistence_manifest": realm_genesis_manifest,
            "retirement_budget": realm_budget,
            "strict_serializable_one_selector_cas": True,
        },
        "higher authority registry transaction contract",
    )
    require_exact(
        set(realm_profile["retirement_budget"]["reserve_covers"]),
        {
            "TARGET_STORE_AMBIGUITY",
            "FULL_ISOLATION_ENVELOPE_CUT",
            "MAXIMUM_SURVIVAL_WAITING_RECORD",
            "PERMANENT_REALM_TOMBSTONE",
        },
        "higher authority registry closure reserve",
    )
    realm_genesis_id = (
        "AUTHORITY_REALM_ENROLLMENT_REGISTRY_GENESIS_FROM_PROVISIONING_AUTHORITY"
    )
    require_exact(
        selectors[realm_selector_id]["generic_receipt"],
        realm_commit,
        "higher authority generic commit receipt",
    )
    for realm_event in selectors[realm_selector_id]["events"]:
        realm_event_id = realm_event["event_id"]
        genesis_realm_event = realm_event_id == realm_genesis_id
        contract = realm_event["authority_realm_registry_contract"]
        require_exact(
            contract["linearization"],
            "ONE_STRICT_SERIALIZABLE_DURABLE_HIGHER_ROOT_CAS_OR_NO_WRITE",
            f"{realm_event_id}: higher-root linearization",
        )
        require_exact(
            contract["qualification"],
            realm_qualification,
            f"{realm_event_id}: higher-root qualification",
        )
        require_exact(
            contract["retirement_budget"],
            realm_budget,
            f"{realm_event_id}: higher-root retirement budget",
        )
        require(
            realm_qualification_receipt
            in {item["artifact"] for item in realm_event["consumes"]},
            f"{realm_event_id}: missing higher-root qualification receipt",
        )
        require(
            local_security_projection
            not in {item["artifact"] for item in realm_event["consumes"]},
            f"{realm_event_id}: external higher root uses local realm security",
        )
        cas_payloads = [
            item
            for item in realm_event["atomic_pre_cas_payloads"]
            if item["artifact"] == realm_cas
        ]
        require_exact(
            len(cas_payloads),
            0 if genesis_realm_event else 1,
            f"{realm_event_id}: higher-root CAS payload count",
        )
        expected_manifest = (
            realm_genesis_manifest if genesis_realm_event else realm_manifest
        )
        sidecar_dependencies = {
            item["artifact"]: set(item["depends_on"])
            for item in realm_event["post_cas_sidecars"]
        }
        require_exact(
            sidecar_dependencies[expected_manifest],
            set(sidecar_dependencies) - {expected_manifest},
            f"{realm_event_id}: higher-root manifest dependency closure",
        )
        require_exact(
            realm_event["post_cas_sidecars"][-1]["artifact"],
            expected_manifest,
            f"{realm_event_id}: higher-root manifest order",
        )
        if not genesis_realm_event:
            for artifact, dependencies in sidecar_dependencies.items():
                if artifact in {realm_commit, realm_manifest}:
                    continue
                require(
                    realm_commit in dependencies,
                    (
                        f"{realm_event_id}: specialized receipt {artifact} "
                        "does not depend on higher-root commit"
                    ),
                )

    realm_states = set(
        domains[("AUTHORITY_REALM_ENROLLMENT_REGISTRY", "REALM_ENROLLMENT_ENTRY")][
            "states"
        ]
    )
    require_exact(
        realm_states,
        {
            "ABSENT",
            "RESERVED_FOR_EXACT_STORE",
            "INSTALLED",
            "LOST_DOMAIN_ISOLATION_CUT_WAITING",
            "PERMANENTLY_RETIRED",
        },
        "higher authority realm enrollment states",
    )
    require_exact(
        event_edges(
            (
                "AUTHORITY_REALM_ENROLLMENT_REGISTRY",
                "CANCEL_RESERVED_AUTHORITY_REALM_ENROLLMENT_BEFORE_DOMAIN_GENESIS",
            ),
            "REALM_ENROLLMENT_ENTRY",
        ),
        {("RESERVED_FOR_EXACT_STORE", "PERMANENTLY_RETIRED")},
        "pre-domain realm cancellation edge",
    )
    require_exact(
        event_edges(
            (
                "AUTHORITY_REALM_ENROLLMENT_REGISTRY",
                "PERMANENTLY_RETIRE_AUTHORITY_REALM_ENROLLMENT",
            ),
            "REALM_ENROLLMENT_ENTRY",
        ),
        {
            ("RESERVED_FOR_EXACT_STORE", "PERMANENTLY_RETIRED"),
            ("INSTALLED", "PERMANENTLY_RETIRED"),
        },
        "realm retirement confirm/reply-loss closure",
    )
    require_exact(
        event_edges(
            (
                "AUTHORITY_REALM_ENROLLMENT_REGISTRY",
                "INSTALL_AUTHORITY_REALM_EXTERNAL_ISOLATION_CUT_AFTER_DOMAIN_STATE_LOSS",
            ),
            "REALM_ENROLLMENT_ENTRY",
        ),
        {
            (
                "RESERVED_FOR_EXACT_STORE",
                "LOST_DOMAIN_ISOLATION_CUT_WAITING",
            ),
            ("INSTALLED", "LOST_DOMAIN_ISOLATION_CUT_WAITING"),
        },
        "realm external-isolation cut edges",
    )
    realm_profile = data["authority_realm_enrollment_registry_profile"]
    realm_loss_profile = realm_profile["lost_domain_external_cut"]
    require_exact(
        set(realm_loss_profile["last_known_branches"]),
        {
            "RESERVATION_ONLY_NO_AUTHENTICATED_DOMAIN_COMMITMENT",
            "EXACT_LAST_AUTHENTICATED_DOMAIN_COMMITMENT",
        },
        "realm lost-domain last-known branches",
    )
    require_exact(
        set(realm_loss_profile["causes"]),
        {
            "DOMAIN_SELECTOR_LOST",
            "REQUIRED_CORE_OR_CLOSURE_GRAPH_UNRECOVERABLE",
            "STORE_ATOMICITY_OR_COMMIT_CONTINUITY_INVALID",
        },
        "realm lost-domain causes",
    )
    realm_cut_event = events[
        (
            "AUTHORITY_REALM_ENROLLMENT_REGISTRY",
            "INSTALL_AUTHORITY_REALM_EXTERNAL_ISOLATION_CUT_AFTER_DOMAIN_STATE_LOSS",
        )
    ]
    expected_realm_cut_cases = {
        (f"{source_state}__{last_known_branch}__{cause}")
        for source_state, last_known_branch in (
            (
                "RESERVED_FOR_EXACT_STORE",
                "RESERVATION_ONLY_NO_AUTHENTICATED_DOMAIN_COMMITMENT",
            ),
            (
                "RESERVED_FOR_EXACT_STORE",
                "EXACT_LAST_AUTHENTICATED_DOMAIN_COMMITMENT",
            ),
            (
                "INSTALLED",
                "EXACT_LAST_AUTHENTICATED_DOMAIN_COMMITMENT",
            ),
        )
        for cause in (
            "DOMAIN_SELECTOR_LOST",
            "REQUIRED_CORE_OR_CLOSURE_GRAPH_UNRECOVERABLE",
            "STORE_ATOMICITY_OR_COMMIT_CONTINUITY_INVALID",
        )
    }
    require_exact(
        {case["semantic_case_id"] for case in realm_cut_event["transition_cases"]},
        expected_realm_cut_cases,
        "realm external-isolation cut semantic closure",
    )
    realm_cut_contract = realm_cut_event["lost_domain_external_cut_contract"]
    require_exact(
        realm_cut_contract["last_commitment_authority"],
        "HISTORICAL_SCOPE_INPUT_ONLY_NEVER_CURRENTNESS",
        "realm lost-domain last commitment authority",
    )
    require_exact(
        realm_cut_contract["unknown_default_missing_extra_or_mixed_axis"],
        "REJECT",
        "realm lost-domain unknown branch",
    )
    for binding in (
        (
            "CLOSED_EXTERNAL_CUT_CAUSE_IS_DOMAIN_SELECTOR_LOST_REQUIRED_"
            "CORE_OR_CLOSURE_GRAPH_UNRECOVERABLE_OR_STORE_ATOMICITY_OR_"
            "COMMIT_CONTINUITY_INVALID"
        ),
        (
            "CLOSED_LAST_KNOWN_BRANCH_IS_RESERVATION_ONLY_NO_AUTHENTICATED_"
            "DOMAIN_COMMITMENT_OR_EXACT_LAST_AUTHENTICATED_DOMAIN_COMMITMENT"
        ),
        (
            "RESERVATION_ONLY_BRANCH_ACCEPTS_RESERVED_ENTRY_ONLY_AS_"
            "AMBIGUOUS_LAST_AUTHENTICATED_EVIDENCE_AND_FORBIDS_INVENTED_"
            "DOMAIN_COMMITMENT_OR_NONGENESIS_PROOF"
        ),
    ):
        require(
            binding in realm_cut_event["pre_cas_content"]["required_bindings"],
            f"realm external-isolation cut lacks {binding}",
        )
    require_exact(
        event_edges(
            (
                "AUTHORITY_REALM_ENROLLMENT_REGISTRY",
                "PERMANENTLY_RETIRE_AUTHORITY_REALM_ENROLLMENT_AFTER_DOMAIN_STATE_LOSS",
            ),
            "REALM_ENROLLMENT_ENTRY",
        ),
        {
            (
                "LOST_DOMAIN_ISOLATION_CUT_WAITING",
                "PERMANENTLY_RETIRED",
            )
        },
        "realm lost-domain horizon retirement edge",
    )
    lost_realm_retirement = events[
        (
            "AUTHORITY_REALM_ENROLLMENT_REGISTRY",
            "PERMANENTLY_RETIRE_AUTHORITY_REALM_ENROLLMENT_AFTER_DOMAIN_STATE_LOSS",
        )
    ]
    require_exact(
        lost_realm_retirement["deadline_conditions"]["mode"],
        "REQUIRED",
        "lost-realm survival deadline mode",
    )
    require_exact(
        {
            (
                condition["deadline_kind"],
                condition["purpose"],
                condition["comparison"],
                condition["clock_authority"],
            )
            for condition in lost_realm_retirement["deadline_conditions"]["conditions"]
        },
        {
            (
                "MAXIMUM_POST_CUT_AUTHORITY_SURVIVAL",
                "EXPIRY_AT_OR_AFTER_EXCLUSIVE_DEADLINE",
                "AT_OR_AFTER",
                "TRUSTED_PROVISIONING_AUTHORITY_MONOTONIC_CLOCK",
            )
        },
        "lost-realm survival deadline condition",
    )
    require(
        (
            "authority-realm-external-isolation-cut-receipt-type::"
            "AuthorityRealmExternalIsolationCutReceipt"
        )
        in {item["artifact"] for item in lost_realm_retirement["consumes"]},
        "lost-realm retirement lacks exact cut receipt",
    )
    require_exact(
        realm_loss_profile["checked_t0_plus_maximum_survival_overflow"],
        "REMAIN_LOST_DOMAIN_ISOLATION_CUT_WAITING_FOREVER",
        "lost-realm checked horizon overflow",
    )
    require_exact(
        realm_loss_profile["exact_deadline_equality"],
        "FIRST_PASSING_INSTANT_WHEN_REPRESENTABLE",
        "lost-realm deadline equality",
    )
    lost_horizon = lost_realm_retirement["lost_domain_retirement_horizon_contract"]
    require_exact(
        lost_horizon["arithmetic"],
        "CHECKED_T0_PLUS_DURATION",
        "lost-realm horizon arithmetic",
    )
    require_exact(
        lost_horizon["equality"],
        "PASS",
        "lost-realm horizon equality",
    )
    require_exact(
        lost_horizon["overflow"],
        ("NO_RETIREMENT_REMAIN_WAITING_FOREVER_NO_WRAP_OR_SHORTER_HORIZON"),
        "lost-realm horizon overflow behavior",
    )
    for event_id in (
        "CANCEL_RESERVED_AUTHORITY_REALM_ENROLLMENT_BEFORE_DOMAIN_GENESIS",
        "PERMANENTLY_RETIRE_AUTHORITY_REALM_ENROLLMENT",
        "INSTALL_AUTHORITY_REALM_EXTERNAL_ISOLATION_CUT_AFTER_DOMAIN_STATE_LOSS",
        "PERMANENTLY_RETIRE_AUTHORITY_REALM_ENROLLMENT_AFTER_DOMAIN_STATE_LOSS",
    ):
        require(
            "authority_transaction_contract"
            not in events[("AUTHORITY_REALM_ENROLLMENT_REGISTRY", event_id)],
            f"{event_id}: higher authority must remain outside enrolled realm",
        )

    require_exact(
        set(domains[("AUTHORITY_TRANSACTION_DOMAIN", "ROOT")]["states"]),
        {
            "ABSENT_NEVER_USED",
            "GENESIS_CANCELED_TOMBSTONE",
            "PENDING_REALM_CONFIRMATION",
            "ACTIVE",
            "RETIREMENT_DRAIN_ONLY",
            "PERMANENTLY_RETIRED",
        },
        "authority transaction domain states",
    )
    require_exact(
        domains[("AUTHORITY_TRANSACTION_DOMAIN", "ROOT")]["absence_semantics"],
        "EXACT_SELECTOR_ABSENCE_WITH_NEVER_REUSE_TOMBSTONE",
        "authority transaction domain selector absence semantics",
    )
    require_exact(
        set(
            domains[
                (
                    "AUTHORITY_TRANSACTION_DOMAIN",
                    "PARTICIPANT_REGISTRY_ENTRY",
                )
            ]["states"]
        ),
        {
            "ABSENT",
            "REGISTERED_ACTIVE",
            "TERMINAL_RETAINED",
            "LOST_STATE_PERMANENTLY_FENCED",
        },
        "authority participant registry states",
    )
    require_exact(
        event_edges(
            (
                "AUTHORITY_TRANSACTION_DOMAIN",
                "AUTHORITY_TRANSACTION_DOMAIN_GENESIS_FROM_ENROLLMENT",
            ),
            "ROOT",
        ),
        {("ABSENT_NEVER_USED", "PENDING_REALM_CONFIRMATION")},
        "authority domain genesis pending-confirmation edge",
    )
    require_exact(
        event_edges(
            (
                "AUTHORITY_TRANSACTION_DOMAIN",
                "ACTIVATE_AUTHORITY_TRANSACTION_DOMAIN_AFTER_REALM_CONFIRMATION",
            ),
            "ROOT",
        ),
        {("PENDING_REALM_CONFIRMATION", "ACTIVE")},
        "authority domain activation edge",
    )
    require_exact(
        event_edges(
            (
                "AUTHORITY_TRANSACTION_DOMAIN",
                "CANCEL_UNCONFIRMED_AUTHORITY_TRANSACTION_DOMAIN",
            ),
            "ROOT",
        ),
        {("PENDING_REALM_CONFIRMATION", "PERMANENTLY_RETIRED")},
        "authority domain unconfirmed cancellation edge",
    )
    pre_genesis_cancel = events[
        (
            "AUTHORITY_TRANSACTION_DOMAIN",
            "CANCEL_AUTHORITY_TRANSACTION_DOMAIN_GENESIS_BEFORE_CREATION",
        )
    ]
    require(
        "authority_transaction_contract" not in pre_genesis_cancel,
        "pre-genesis cancellation cannot claim a nonexistent domain",
    )
    require_exact(
        event_edges(
            (
                "AUTHORITY_TRANSACTION_DOMAIN",
                "CANCEL_AUTHORITY_TRANSACTION_DOMAIN_GENESIS_BEFORE_CREATION",
            ),
            "ROOT",
        ),
        {("ABSENT_NEVER_USED", "GENESIS_CANCELED_TOMBSTONE")},
        "authority domain pre-genesis cancellation tombstone edge",
    )
    require_exact(
        event_edges(
            (
                "AUTHORITY_TRANSACTION_DOMAIN",
                "BEGIN_AUTHORITY_TRANSACTION_DOMAIN_RETIREMENT",
            ),
            "ROOT",
        ),
        {("ACTIVE", "RETIREMENT_DRAIN_ONLY")},
        "authority domain drain edge",
    )
    require_exact(
        event_edges(
            (
                "AUTHORITY_TRANSACTION_DOMAIN",
                "FENCE_LOST_AUTHORITY_TRANSACTION_DOMAIN_PARTICIPANT_AFTER_ISOLATION",
            ),
            "PARTICIPANT_REGISTRY_ENTRY",
        ),
        {
            (
                "REGISTERED_ACTIVE",
                "LOST_STATE_PERMANENTLY_FENCED",
            )
        },
        "lost participant isolation edge",
    )
    lost_event = events[
        (
            "AUTHORITY_TRANSACTION_DOMAIN",
            "FENCE_LOST_AUTHORITY_TRANSACTION_DOMAIN_PARTICIPANT_AFTER_ISOLATION",
        )
    ]
    for binding in (
        "PROOF_OF_MISSING_OR_AMBIGUOUS_PARTICIPANT_CURRENTNESS",
        "INDEPENDENT_COMPLETE_PERMANENT_ISOLATION_PROOF_FOR_PARTICIPANT_AUTHORITY_FOOTPRINT",
        "FORBID_INVENTED_ABSENCE_HEAD_OR_SELECTOR_VERSION_AS_PARTICIPANT_CURRENTNESS",
    ):
        require(
            binding in lost_event["pre_cas_content"]["required_bindings"],
            f"lost participant event lacks {binding}",
        )
    lost_contract = lost_event["authority_transaction_contract"]
    require_exact(
        lost_contract["participant_set_mode"],
        (
            "DOMAIN_STATE_PLUS_COMPLETE_INTACT_CLOSURE_PARTICIPANTS_"
            "LOST_TARGET_EVIDENCE_ONLY"
        ),
        "lost participant set mode",
    )
    require_exact(
        lost_contract["lost_target_selector_participation"],
        "STRUCTURALLY_EXCLUDED_NO_EXPECTED_HEAD_OR_CURRENT_VERSION",
        "lost target selector participation",
    )
    require(
        all(
            item["role"] != "EXPECTED_LOST_PARTICIPANT_SELECTOR"
            for item in lost_event["consumes"]
        ),
        "lost participant fence requires the missing selector as current",
    )

    def partition_for(
        key: tuple[str, str],
        state_domain: str,
    ) -> dict[str, Any]:
        matches = [
            item
            for item in events[key]["partition_effects"]
            if item["state_domain"] == state_domain
        ]
        require_exact(
            len(matches),
            1,
            f"{key}: {state_domain} partition count",
        )
        return matches[0]

    genesis_participants = partition_for(
        (
            "AUTHORITY_TRANSACTION_DOMAIN",
            "AUTHORITY_TRANSACTION_DOMAIN_GENESIS_FROM_ENROLLMENT",
        ),
        "PARTICIPANT_REGISTRY_ENTRY",
    )
    require_exact(
        {
            branch["branch_id"]: branch["cardinality"]
            for branch in genesis_participants["branches"]
        },
        {
            "EXACT_DOMAIN_SELF_ENTRY": "EXACTLY_ONE",
            "EXACT_THREE_PRISTINE_CORE_ENTRIES": "EXACTLY_THREE",
        },
        "domain genesis participant partition",
    )
    cancel_participants = partition_for(
        (
            "AUTHORITY_TRANSACTION_DOMAIN",
            "CANCEL_UNCONFIRMED_AUTHORITY_TRANSACTION_DOMAIN",
        ),
        "PARTICIPANT_REGISTRY_ENTRY",
    )
    require_exact(
        {
            (
                branch["branch_id"],
                branch["from_state"],
                branch["to_state"],
                branch["cardinality"],
            )
            for branch in cancel_participants["branches"]
        },
        {
            (
                "EXACT_DOMAIN_SELF_ENTRY",
                "REGISTERED_ACTIVE",
                "TERMINAL_RETAINED",
                "EXACTLY_ONE",
            ),
            (
                "EXACT_THREE_PRISTINE_CORE_ENTRIES",
                "REGISTERED_ACTIVE",
                "TERMINAL_RETAINED",
                "EXACTLY_THREE",
            ),
        },
        "unconfirmed cancellation self/core terminalization",
    )
    final_participants = partition_for(
        (
            "AUTHORITY_TRANSACTION_DOMAIN",
            "FINALIZE_AUTHORITY_TRANSACTION_DOMAIN_RETIREMENT",
        ),
        "PARTICIPANT_REGISTRY_ENTRY",
    )
    final_branches = {
        branch["branch_id"]: branch for branch in final_participants["branches"]
    }
    require(
        {
            "EXACT_REGISTERED_DOMAIN_SELF_TO_TERMINAL",
            "EXACT_PRESENT_CORE_TO_TERMINAL",
            "LOST_CORE_PRESERVED",
            "NONCORE_TERMINAL_PRESERVED",
            "NONCORE_LOST_PRESERVED",
        }
        == set(final_branches),
        "domain finalization participant partition is not closed",
    )
    require_exact(
        (
            final_branches["EXACT_REGISTERED_DOMAIN_SELF_TO_TERMINAL"]["from_state"],
            final_branches["EXACT_REGISTERED_DOMAIN_SELF_TO_TERMINAL"]["to_state"],
            final_branches["EXACT_REGISTERED_DOMAIN_SELF_TO_TERMINAL"]["cardinality"],
        ),
        ("REGISTERED_ACTIVE", "TERMINAL_RETAINED", "EXACTLY_ONE"),
        "domain self finalization branch",
    )
    require_exact(
        final_participants["preterminal_self_requirement"],
        "FORBIDDEN",
        "domain finalization preterminal-self deadlock",
    )
    for event_id in (
        "TERMINALIZE_AUTHORITY_TRANSACTION_DOMAIN_PARTICIPANT",
        "FENCE_LOST_AUTHORITY_TRANSACTION_DOMAIN_PARTICIPANT_AFTER_ISOLATION",
    ):
        _require_binding(
            events,
            ("AUTHORITY_TRANSACTION_DOMAIN", event_id),
            "TARGET_ROLE_IS_NOT_AUTHORITY_TRANSACTION_DOMAIN_STATE"
            if event_id.startswith("FENCE_LOST")
            else (
                "TARGET_ROLE_IS_NOT_AUTHORITY_TRANSACTION_DOMAIN_STATE_OR_"
                "PRISTINE_CORE_FINALIZATION_ENTRY"
            ),
        )

    admission_event = events[
        (
            "AUTHORITY_TRANSACTION_DOMAIN",
            "REGISTER_AUTHORITY_TRANSACTION_DOMAIN_PARTICIPANT",
        )
    ]
    require(
        any(
            item["artifact"] == prior_installed_evidence
            and item["branch_condition"]
            == "ENROLL_BOOTSTRAP_OR_GENESIS_ONLY_EXISTING_SELECTOR"
            for item in admission_event["consumes"]
        ),
        "existing-selector admission lacks exact prior-installed evidence",
    )
    admission_dag = admission_event["participant_admission_dependency_dag"]
    require_exact(
        set(admission_dag["branches"]),
        {
            "INSTALL_FRESH_SELECTOR_WITH_NATIVE_GENESIS",
            "ENROLL_BOOTSTRAP_OR_GENESIS_ONLY_EXISTING_SELECTOR",
        },
        "participant admission branches",
    )
    admission_graphs = {
        branch: require_acyclic_dependency_nodes(
            nodes,
            f"participant admission {branch}",
        )
        for branch, nodes in admission_dag["branches"].items()
    }
    fresh_graph = admission_graphs["INSTALL_FRESH_SELECTOR_WITH_NATIVE_GENESIS"]
    require_exact(
        fresh_graph["PARTICIPANT_ADMISSION_COMMITMENT"],
        {"OWNER_AUTHORIZED_NATIVE_GENESIS_FACT"},
        "fresh admission commitment dependencies",
    )
    require_exact(
        fresh_graph["AUTHORITY_TRANSACTION_CAS_CONDITION"],
        {
            "NATIVE_PARTICIPANT_READ_WRITE_SELECTOR_IDENTITY_SET",
            "OWNER_AUTHORIZED_NATIVE_GENESIS_FACT",
            "PARTICIPANT_ADMISSION_COMMITMENT",
        },
        "fresh admission CAS dependencies",
    )
    for candidate in (
        "CANDIDATE_NATIVE_PARTICIPANT_SELECTOR_HEAD",
        "CANDIDATE_AUTHORITY_TRANSACTION_DOMAIN_STATE_HEAD",
    ):
        require_exact(
            fresh_graph[candidate],
            {
                "AUTHORITY_TRANSACTION_CAS_CONDITION",
                "OWNER_AUTHORIZED_NATIVE_GENESIS_FACT",
                "PARTICIPANT_ADMISSION_COMMITMENT",
            },
            f"{candidate}: dependencies",
        )
    require_exact(
        fresh_graph["SELECTOR_SPECIFIC_NATIVE_GENESIS_COMMIT_RECEIPT"],
        {"AUTHORITY_TRANSACTION_COMMIT_RECEIPT"},
        "selector-specific native genesis receipt dependencies",
    )
    require_exact(
        fresh_graph["NATIVE_PARTICIPANT_GENESIS_RECEIPT"],
        {
            "AUTHORITY_TRANSACTION_COMMIT_RECEIPT",
            "SELECTOR_SPECIFIC_NATIVE_GENESIS_COMMIT_RECEIPT",
        },
        "native genesis receipt dependencies",
    )
    require_exact(
        fresh_graph["AUTHORITY_TRANSACTION_DOMAIN_PARTICIPANT_ADMISSION_RECEIPT"],
        {
            "AUTHORITY_TRANSACTION_COMMIT_RECEIPT",
            "NATIVE_PARTICIPANT_GENESIS_RECEIPT",
            "SELECTOR_SPECIFIC_NATIVE_GENESIS_COMMIT_RECEIPT",
        },
        "participant admission receipt dependencies",
    )
    require_exact(
        fresh_graph["AUTHORITY_TRANSACTION_PERSISTENCE_MANIFEST"],
        {
            "AUTHORITY_TRANSACTION_COMMIT_RECEIPT",
            "AUTHORITY_TRANSACTION_DOMAIN_PARTICIPANT_ADMISSION_RECEIPT",
            "NATIVE_PARTICIPANT_GENESIS_RECEIPT",
            "SELECTOR_SPECIFIC_NATIVE_GENESIS_COMMIT_RECEIPT",
        },
        "fresh admission persistence-manifest dependencies",
    )
    existing_graph = admission_graphs[
        "ENROLL_BOOTSTRAP_OR_GENESIS_ONLY_EXISTING_SELECTOR"
    ]
    require_exact(
        existing_graph["AUTHORITY_TRANSACTION_PERSISTENCE_MANIFEST"],
        {
            "AUTHORITY_TRANSACTION_COMMIT_RECEIPT",
            "AUTHORITY_TRANSACTION_DOMAIN_PARTICIPANT_ADMISSION_RECEIPT",
        },
        "existing-selector admission persistence-manifest dependencies",
    )
    require(
        {
            "AUTHORITY_TRANSACTION_CAS_CONDITION",
            "CANDIDATE_OR_SUCCESSOR_HEAD",
            "CURRENT_TRANSACTION_RECEIPT",
            "NATIVE_PARTICIPANT_GENESIS_RECEIPT_CREATED_BY_THIS_TRANSACTION",
            "PARTICIPANT_ADMISSION_RECEIPT",
        }.issubset(set(admission_dag["commitment_excludes"])),
        "participant admission commitment exclusion set is incomplete",
    )
    admission_case_ids = {
        case["semantic_case_id"] for case in admission_event["transition_cases"]
    }
    require_exact(
        admission_case_ids,
        set(admission_dag["branches"]),
        "participant admission semantic branches",
    )
    atomic_admission_artifacts = {
        item["artifact"] for item in admission_event["atomic_pre_cas_payloads"]
    }
    require(
        {
            (
                "owner-authorized-native-genesis-fact-type::"
                "OwnerAuthorizedNativeGenesisFact"
            ),
            (
                "authority-transaction-domain-participant-admission-"
                "commitment-type::"
                "AuthorityTransactionDomainParticipantAdmissionCommitment"
            ),
            (
                "native-participant-read-write-selector-identity-set-type::"
                "NativeParticipantReadWriteSelectorIdentitySet"
            ),
        }.issubset(atomic_admission_artifacts),
        "participant admission pre-CAS artifacts are incomplete",
    )
    mutated_nodes = [
        {
            "node": node,
            "depends_on": sorted(
                dependencies
                | (
                    {"CANDIDATE_NATIVE_PARTICIPANT_SELECTOR_HEAD"}
                    if node == "PARTICIPANT_ADMISSION_COMMITMENT"
                    else set()
                )
            ),
        }
        for node, dependencies in fresh_graph.items()
    ]
    mutant_rejected = False
    try:
        require_acyclic_dependency_nodes(
            mutated_nodes,
            "ordinary participant commitment-binds-candidate mutant",
        )
    except ClosureCheckError:
        mutant_rejected = True
    require(
        mutant_rejected,
        "ordinary participant candidate-cycle mutant survived",
    )

    fresh_native_events = {
        (
            "SECURITY_AUTHORITY",
            "SECURITY_AUTHORITY_STATE_GENESIS_FROM_TRUST_ROOT_ENROLLMENT",
        ): {
            "native_fact": (
                "security-authority-transition-fact-type::"
                "SecurityAuthorityTransitionFact"
            ),
            "native_receipt": (
                "security-authority-state-commit-receipt-type::"
                "SecurityAuthorityStateCommitReceipt"
            ),
            "selector_absence_role": (
                "FRESH_NATIVE_SELECTOR_ABSENCE_AND_NEVER_USED_PROOF"
            ),
        },
        (
            "BODY_SESSION_CONTROL",
            "BODY_SESSION_CONTROL_GENESIS_FROM_SESSION_CREATION",
        ): {
            "native_fact": (
                "required-generation-child-genesis-joint-fact-type::"
                "RequiredGenerationChildGenesisJointFact"
            ),
            "native_receipt": (
                "body-session-control-state-commit-receipt-type::"
                "BodySessionControlStateCommitReceipt"
            ),
            "selector_absence_role": (
                "FRESH_NATIVE_SELECTOR_ABSENCE_AND_NEVER_USED_PROOF"
            ),
        },
        (
            "LOGICAL_SESSION_NAMESPACE_REGISTRY",
            "REGISTER_SOURCE_LOGICAL_SESSION_LINEAGE",
        ): {
            "native_fact": (
                "logical-session-generation-lineage-genesis-fact-type::"
                "LogicalSessionGenerationLineageGenesisFact"
            ),
            "native_receipt": (
                "logical-session-generation-lineage-commit-receipt-type::"
                "LogicalSessionGenerationLineageCommitReceipt"
            ),
            "selector_absence_role": (
                "FRESH_NATIVE_SELECTOR_ABSENCE_AND_NEVER_USED_PROOF"
            ),
        },
        (
            "ACTUATION_AUTHORITY_DOMAIN",
            "ACTUATION_AUTHORITY_DOMAIN_REGISTRY_GENESIS_FROM_"
            "PHYSICAL_JURISDICTION_ENROLLMENT",
        ): {
            "native_fact": (
                "physical-actuation-jurisdiction-enrollment-fact-type::"
                "PhysicalActuationJurisdictionEnrollmentFact"
            ),
            "native_receipt": (
                "actuation-authority-domain-registry-commit-receipt-type::"
                "ActuationAuthorityDomainRegistryCommitReceipt"
            ),
            "selector_absence_role": (
                "FRESH_NATIVE_SELECTOR_ABSENCE_AND_NEVER_USED_PROOF"
            ),
        },
        (
            "INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_REGISTRY",
            "INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_REGISTRY_GENESIS_"
            "FROM_ANCHOR_AUTHORITY_ENROLLMENT",
        ): {
            "native_fact": (
                "independent-anchor-namespace-reservation-registry-genesis-"
                "fact-type::"
                "IndependentAnchorNamespaceReservationRegistryGenesisFact"
            ),
            "native_receipt": (
                "independent-anchor-namespace-reservation-registry-commit-"
                "receipt-type::"
                "IndependentAnchorNamespaceReservationRegistryCommitReceipt"
            ),
            "selector_absence_role": (
                "TYPED_RESERVATION_REGISTRY_SELECTOR_ABSENCE_AND_NEVER_USED_PROOF"
            ),
        },
        (
            "OBSERVER_AUTHORIZATION",
            "OBSERVER_AUTHORIZATION_STATE_GENESIS_FROM_SESSION_CREATION",
        ): {
            "native_fact": (
                "required-generation-child-genesis-joint-fact-type::"
                "RequiredGenerationChildGenesisJointFact"
            ),
            "native_receipt": (
                "observer-authorization-state-commit-receipt-type::"
                "ObserverAuthorizationStateCommitReceipt"
            ),
            "selector_absence_role": (
                "TYPED_OBSERVER_CHILD_SELECTOR_ABSENCE_AND_NEVER_USED_PROOF"
            ),
        },
        (
            "OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR",
            "CREATE_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR",
        ): {
            "native_fact": (
                "observer-grant-challenge-exposure-anchor-genesis-fact-type::"
                "ObserverGrantChallengeExposureAnchorGenesisFact"
            ),
            "native_receipt": (
                "observer-grant-challenge-exposure-anchor-commit-receipt-type::"
                "ObserverGrantChallengeExposureAnchorCommitReceipt"
            ),
            "selector_absence_role": (
                "TYPED_ANCHOR_SELECTOR_ABSENCE_AND_NEVER_USED_PROOF"
            ),
        },
        (
            "SIMULATION_SESSION_STATE",
            "SIMULATION_SESSION_STATE_GENESIS_FROM_GENERATION_CREATION",
        ): {
            "native_fact": (
                "required-generation-child-genesis-joint-fact-type::"
                "RequiredGenerationChildGenesisJointFact"
            ),
            "native_receipt": (
                "simulation-session-state-commit-receipt-type::"
                "SimulationSessionStateCommitReceipt"
            ),
            "selector_absence_role": (
                "TYPED_SIMULATION_SELECTOR_ABSENCE_AND_NEVER_USED_PROOF"
            ),
        },
    }
    candidate_joint_participant_events = {
        (
            "INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_REGISTRY",
            "CREATE_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR",
        ),
        (
            "LOGICAL_SESSION_GENERATION_LINEAGE",
            "CONSUME_REQUIRED_GENERATION_CHILD_SELECTOR_MARKER_AT_"
            "BODY_SESSION_CONTROL_STATE_NATIVE_GENESIS",
        ),
        (
            "LOGICAL_SESSION_GENERATION_LINEAGE",
            "CONSUME_REQUIRED_GENERATION_CHILD_SELECTOR_MARKER_AT_"
            "OBSERVER_AUTHORIZATION_STATE_NATIVE_GENESIS",
        ),
        (
            "LOGICAL_SESSION_GENERATION_LINEAGE",
            "CONSUME_REQUIRED_GENERATION_CHILD_SELECTOR_MARKER_AT_"
            "SIMULATION_SESSION_STATE_NATIVE_GENESIS",
        ),
    }
    candidate_admission_events = {
        key
        for key, event in events.items()
        if event.get("authority_transaction_contract", {}).get("participant_set_mode")
        == "CANDIDATE_PARTICIPANT_ADMISSION"
    }
    require_exact(
        candidate_admission_events,
        set(fresh_native_events) | candidate_joint_participant_events,
        "candidate participant-admission event closure",
    )
    for key in candidate_joint_participant_events:
        participant = events[key]
        require(
            "fresh_native_participant_admission_contract" not in participant,
            f"{key}: non-coordinator joint participant claims fresh admission",
        )
        require(
            "joint_selector_transaction_profile_ref" in participant,
            f"{key}: candidate admission participant lacks a joint transaction",
        )

    for key, native_contract in fresh_native_events.items():
        fresh_event = events[key]
        fresh_label = f"{key[0]}.{key[1]}"
        require_exact(
            fresh_event["authority_transaction_contract"]["participant_set_mode"],
            "CANDIDATE_PARTICIPANT_ADMISSION",
            f"{fresh_label}: fresh participant-admission mode",
        )
        require_exact(
            fresh_event["authority_transaction_contract"]["domain_state"],
            (
                "ACTIVE_OR_RETIREMENT_DRAIN_ONLY_FOR_EXACT_CLOSURE_EVENT"
                if key[0] == "SIMULATION_SESSION_STATE"
                else "ACTIVE"
            ),
            f"{fresh_label}: fresh admission domain state",
        )
        fresh_contract = fresh_event["fresh_native_participant_admission_contract"]
        require_exact(
            fresh_contract["branch"],
            "INSTALL_FRESH_SELECTOR_WITH_NATIVE_GENESIS",
            f"{fresh_label}: fresh admission branch",
        )
        require_exact(
            fresh_contract["native_genesis_fact"],
            native_contract["native_fact"],
            f"{fresh_label}: native genesis fact",
        )
        require_exact(
            fresh_contract["selector_absence"],
            "EXACT_TYPED_NEVER_USED_SELECTOR_NONMEMBERSHIP",
            f"{fresh_label}: native selector absence",
        )
        require_exact(
            fresh_contract["native_selector_commit_receipt"],
            native_contract["native_receipt"],
            f"{fresh_label}: native selector commit receipt",
        )
        require_exact(
            fresh_contract["atomic_compares"].count(
                "ACTIVE_AUTHORITY_TRANSACTION_DOMAIN_STATE"
            ),
            1,
            f"{fresh_label}: exact ACTIVE-domain compare",
        )
        if key[0] == "BODY_SESSION_CONTROL":
            require(
                "NO_EXISTING_BODY_SESSION_CONTROL_PARTICIPANT_ENTRY"
                in fresh_contract["atomic_compares"],
                f"{fresh_label}: body participant nonmembership",
            )
        require_exact(
            fresh_contract["unknown_default_or_precreated_selector"],
            "REJECT",
            f"{fresh_label}: precreated-selector handling",
        )
        require(
            any(
                item["role"] == native_contract["selector_absence_role"]
                for item in fresh_event["consumes"]
            ),
            f"{fresh_label}: fresh native selector absence proof missing",
        )
        fresh_atomic = {
            item["artifact"] for item in fresh_event["atomic_pre_cas_payloads"]
        }
        require(
            {
                participant_admission_commitment,
                cas_condition,
            }.issubset(fresh_atomic),
            f"{fresh_label}: fresh admission pre-CAS artifacts incomplete",
        )
        native_identity_occurrences = sum(
            item["artifact"] == native_identity_set
            for collection in (
                fresh_event["atomic_pre_cas_payloads"],
                fresh_event["consumes"],
            )
            for item in collection
        )
        require_exact(
            native_identity_occurrences,
            1,
            f"{fresh_label}: native selector identity-set occurrence",
        )
        fresh_sidecars = {
            item["artifact"]: item for item in fresh_event["post_cas_sidecars"]
        }
        native_selector_commit_receipt = native_contract["native_receipt"]
        local_required_sidecars = {
            transaction_receipt,
            native_genesis_receipt,
            participant_admission_receipt,
            persistence_manifest,
        }
        joint_receipt = (
            "joint-selector-transaction-commit-receipt-type::"
            "JointSelectorTransactionCommitReceipt"
        )
        namespace_composite = key[0] == "LOGICAL_SESSION_NAMESPACE_REGISTRY"
        if namespace_composite:
            local_required_sidecars.add(joint_receipt)
        else:
            local_required_sidecars.add(native_selector_commit_receipt)
        require(
            local_required_sidecars.issubset(fresh_sidecars),
            f"{fresh_label}: fresh admission receipt DAG incomplete",
        )
        if namespace_composite:
            joint_sidecar = fresh_sidecars[joint_receipt]
            namespace_commit_receipt = (
                "logical-session-namespace-registry-commit-receipt-type::"
                "LogicalSessionNamespaceRegistryCommitReceipt"
            )
            source_registration_profile = data["joint_selector_transaction_profiles"][
                "JTX_SOURCE_LINEAGE_REGISTRATION"
            ]
            require_exact(
                {
                    item["generic_receipt"]
                    for item in source_registration_profile["participants"]
                },
                {
                    namespace_commit_receipt,
                    native_selector_commit_receipt,
                    (
                        "observer-grant-source-issuance-index-commit-receipt-"
                        "type::ObserverGrantSourceIssuanceIndexCommitReceipt"
                    ),
                },
                f"{fresh_label}: joint selector commit-receipt closure",
            )
            require(
                "ALL_DECLARED_WRITING_PARTICIPANT_GENERIC_COMMIT_RECEIPTS"
                in joint_sidecar["additional_bindings"],
                f"{fresh_label}: joint receipt omits participant commits",
            )
            require(
                {
                    transaction_receipt,
                    namespace_commit_receipt,
                }.issubset(set(joint_sidecar["depends_on"])),
                f"{fresh_label}: joint receipt local dependency closure",
            )
        else:
            require(
                transaction_receipt
                in fresh_sidecars[native_selector_commit_receipt]["depends_on"],
                (
                    f"{fresh_label}: native selector receipt precedes "
                    "transaction receipt"
                ),
            )
        native_receipt_dependencies = {
            transaction_receipt,
            (joint_receipt if namespace_composite else native_selector_commit_receipt),
        }
        require(
            native_receipt_dependencies.issubset(
                set(fresh_sidecars[native_genesis_receipt]["depends_on"])
            ),
            f"{fresh_label}: native genesis receipt dependency closure",
        )
        admission_dependencies = {
            transaction_receipt,
            native_genesis_receipt,
            (joint_receipt if namespace_composite else native_selector_commit_receipt),
        }
        require(
            admission_dependencies.issubset(
                set(fresh_sidecars[participant_admission_receipt]["depends_on"])
            ),
            f"{fresh_label}: admission receipt dependency closure",
        )
        post_persistence_sidecars = {
            artifact
            for artifact, sidecar in fresh_sidecars.items()
            if persistence_manifest in sidecar["depends_on"]
        }
        require_exact(
            set(fresh_sidecars[persistence_manifest]["depends_on"]),
            set(fresh_sidecars) - {persistence_manifest} - post_persistence_sidecars,
            f"{fresh_label}: persistence manifest dependency closure",
        )
        fresh_dag = fresh_event.get("participant_admission_dependency_dag")
        if fresh_dag is None:
            require(
                key
                in {
                    (
                        "INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_REGISTRY",
                        "INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_REGISTRY_"
                        "GENESIS_FROM_ANCHOR_AUTHORITY_ENROLLMENT",
                    ),
                    (
                        "OBSERVER_AUTHORIZATION",
                        "OBSERVER_AUTHORIZATION_STATE_GENESIS_FROM_SESSION_CREATION",
                    ),
                    (
                        "OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR",
                        "CREATE_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR",
                    ),
                    (
                        "SIMULATION_SESSION_STATE",
                        "SIMULATION_SESSION_STATE_GENESIS_FROM_GENERATION_CREATION",
                    ),
                },
                f"{fresh_label}: participant-admission DAG is absent",
            )
            continue
        require_exact(
            set(fresh_dag["branches"]),
            {"INSTALL_FRESH_SELECTOR_WITH_NATIVE_GENESIS"},
            f"{fresh_label}: fresh admission DAG branches",
        )
        fresh_graph = require_acyclic_dependency_nodes(
            fresh_dag["branches"]["INSTALL_FRESH_SELECTOR_WITH_NATIVE_GENESIS"],
            f"{fresh_label}: fresh admission DAG",
        )
        require_exact(
            fresh_graph["SELECTOR_SPECIFIC_NATIVE_GENESIS_COMMIT_RECEIPT"],
            {"AUTHORITY_TRANSACTION_COMMIT_RECEIPT"},
            f"{fresh_label}: selector-specific receipt dependencies",
        )
        if namespace_composite:
            require_exact(
                fresh_graph["JOINT_SELECTOR_TRANSACTION_COMMIT_RECEIPT"],
                {
                    "AUTHORITY_TRANSACTION_COMMIT_RECEIPT",
                    "SELECTOR_SPECIFIC_NATIVE_GENESIS_COMMIT_RECEIPT",
                },
                f"{fresh_label}: joint receipt dependencies",
            )
        conceptual_joint_dependency = (
            {"JOINT_SELECTOR_TRANSACTION_COMMIT_RECEIPT"}
            if namespace_composite
            else set()
        )
        require_exact(
            fresh_graph["NATIVE_PARTICIPANT_GENESIS_RECEIPT"],
            {
                "AUTHORITY_TRANSACTION_COMMIT_RECEIPT",
                "SELECTOR_SPECIFIC_NATIVE_GENESIS_COMMIT_RECEIPT",
            }
            | conceptual_joint_dependency,
            f"{fresh_label}: native receipt dependencies",
        )
        require_exact(
            fresh_graph["AUTHORITY_TRANSACTION_DOMAIN_PARTICIPANT_ADMISSION_RECEIPT"],
            {
                "AUTHORITY_TRANSACTION_COMMIT_RECEIPT",
                "NATIVE_PARTICIPANT_GENESIS_RECEIPT",
                "SELECTOR_SPECIFIC_NATIVE_GENESIS_COMMIT_RECEIPT",
            }
            | conceptual_joint_dependency,
            f"{fresh_label}: admission DAG terminal dependencies",
        )
        require_exact(
            fresh_graph["AUTHORITY_TRANSACTION_PERSISTENCE_MANIFEST"],
            {
                "AUTHORITY_TRANSACTION_COMMIT_RECEIPT",
                "AUTHORITY_TRANSACTION_DOMAIN_PARTICIPANT_ADMISSION_RECEIPT",
                "NATIVE_PARTICIPANT_GENESIS_RECEIPT",
                "SELECTOR_SPECIFIC_NATIVE_GENESIS_COMMIT_RECEIPT",
            }
            | conceptual_joint_dependency,
            f"{fresh_label}: persistence-manifest DAG dependencies",
        )

    source_registration_profile = data["joint_selector_transaction_profiles"][
        "JTX_SOURCE_LINEAGE_REGISTRATION"
    ]
    source_registration_keys = {
        (
            "LOGICAL_SESSION_NAMESPACE_REGISTRY",
            "REGISTER_SOURCE_LOGICAL_SESSION_LINEAGE",
        ),
        (
            "LOGICAL_SESSION_GENERATION_LINEAGE",
            "LOGICAL_SESSION_GENERATION_LINEAGE_GENESIS_FROM_SERVER_AUTHORITY",
        ),
        (
            "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX",
            (
                "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX_GENESIS_"
                "FROM_SOURCE_LINEAGE_REGISTRATION"
            ),
        ),
    }
    require_exact(
        {
            (item["selector_id"], item["event_id"])
            for item in source_registration_profile["participants"]
        },
        source_registration_keys,
        "source-lineage composite transaction participants",
    )
    require_exact(
        set(source_registration_profile["shared_pre_cas_facts"]),
        {
            (
                "logical-session-namespace-registration-fact-type::"
                "LogicalSessionNamespaceRegistrationFact"
            ),
            (
                "logical-session-generation-lineage-genesis-fact-type::"
                "LogicalSessionGenerationLineageGenesisFact"
            ),
            (
                "observer-grant-source-issuance-index-genesis-fact-type::"
                "ObserverGrantSourceIssuanceIndexGenesisFact"
            ),
        },
        "source-lineage composite receipt-free facts",
    )
    require_exact(
        source_registration_profile["partial_commit_behavior"],
        "IMPOSSIBLE_BY_STORE_PRIMITIVE_OR_EVENT_DISABLED",
        "source-lineage partial-commit behavior",
    )
    for source_registration_key in source_registration_keys:
        source_registration_event = events[source_registration_key]
        require_exact(
            source_registration_event["joint_selector_transaction_profile_ref"],
            "JTX_SOURCE_LINEAGE_REGISTRATION",
            f"{source_registration_key}: composite transaction ref",
        )
        composite_contract = source_registration_event[
            "source_lineage_registration_composite_contract"
        ]
        require_exact(
            composite_contract["partial_visibility_or_commit"],
            "FORBIDDEN",
            f"{source_registration_key}: partial source-lineage install",
        )
        require_exact(
            set(composite_contract["atomic_write_selectors"]),
            {
                "AUTHORITY_TRANSACTION_DOMAIN_STATE",
                "LOGICAL_SESSION_NAMESPACE_REGISTRY",
                "LOGICAL_SESSION_LINEAGE",
                "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX",
            },
            f"{source_registration_key}: composite write selectors",
        )
        require_exact(
            set(
                source_registration_event["authority_transaction_contract"][
                    "write_roles"
                ]
            ),
            {
                "AUTHORITY_TRANSACTION_DOMAIN_STATE",
                "LOGICAL_SESSION_NAMESPACE_REGISTRY",
                "LOGICAL_SESSION_LINEAGE",
                "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX",
            },
            f"{source_registration_key}: authority write roles",
        )
        require(
            set(source_registration_profile["shared_pre_cas_facts"]).issubset(
                {
                    source_registration_event["pre_cas_content"]["artifact"],
                    *(
                        item["artifact"]
                        for item in source_registration_event["atomic_pre_cas_payloads"]
                    ),
                }
            ),
            f"{source_registration_key}: incomplete composite fact pair",
        )

    for selector_id in (
        "SECURITY_AUTHORITY",
        "BODY_SESSION_CONTROL",
        "LOGICAL_SESSION_GENERATION_LINEAGE",
        "ACTUATION_AUTHORITY_DOMAIN",
    ):
        root = domains[(selector_id, "ROOT")]
        require(
            "UNINITIALIZED" not in root["states"],
            f"{selector_id}: conceptual absence remains an installed phase",
        )
        require_exact(
            root["initial_state"],
            "ABSENT_NEVER_USED",
            f"{selector_id}: typed selector absence initial state",
        )
        require_exact(
            root["absence_semantics"],
            "EXACT_SELECTOR_ABSENCE_WITH_NEVER_REUSE_TOMBSTONE",
            f"{selector_id}: selector absence semantics",
        )
    require_exact(
        event_edges(
            (
                "SECURITY_AUTHORITY",
                "SECURITY_AUTHORITY_STATE_GENESIS_FROM_TRUST_ROOT_ENROLLMENT",
            ),
            "ROOT",
        ),
        {("ABSENT_NEVER_USED", "CURRENT")},
        "security authority fresh genesis edge",
    )
    require_exact(
        event_edges(
            (
                "BODY_SESSION_CONTROL",
                "BODY_SESSION_CONTROL_GENESIS_FROM_SESSION_CREATION",
            ),
            "ROOT",
        ),
        {("ABSENT_NEVER_USED", "INSTALLED_CHAIN")},
        "body-control fresh genesis edge",
    )
    require_exact(
        event_edges(
            (
                "LOGICAL_SESSION_GENERATION_LINEAGE",
                "LOGICAL_SESSION_GENERATION_LINEAGE_GENESIS_FROM_SERVER_AUTHORITY",
            ),
            "ROOT",
        ),
        {("ABSENT_NEVER_USED", "NO_GENERATION")},
        "source-lineage fresh genesis edge",
    )
    require_exact(
        event_edges(
            (
                "ACTUATION_AUTHORITY_DOMAIN",
                "ACTUATION_AUTHORITY_DOMAIN_REGISTRY_GENESIS_FROM_"
                "PHYSICAL_JURISDICTION_ENROLLMENT",
            ),
            "ROOT",
        ),
        {("ABSENT_NEVER_USED", "PENDING_FACILITY_CONFIRMATION")},
        "actuation registry fresh genesis edge",
    )
    require(
        (
            "SECURITY_AUTHORITY",
            "PROVISION_FROM_UNINITIALIZED",
        )
        not in events,
        "legacy security-authority genesis event remains",
    )
    security_profile = data["security_authority_state_profile"]
    require_exact(
        security_profile["genesis_mode"],
        "CANDIDATE_PARTICIPANT_ADMISSION",
        "security authority genesis mode profile",
    )
    require_exact(
        security_profile["authority_outside_participant_membership"],
        "NONE",
        "security authority outside participant membership",
    )
    require_exact(
        security_profile["second_local_currentness_root"],
        "FORBIDDEN",
        "security authority second-root rule",
    )
    require_exact(
        security_profile["replacement"],
        "FRESH_AUTHORITY_REALM_KEY_AND_TRANSACTION_DOMAIN_REQUIRED",
        "security authority replacement boundary",
    )
    require_exact(
        security_profile["selector_cardinality"],
        (
            "EXACTLY_ONE_ACTIVE_SECURITY_AUTHORITY_SELECTOR_PER_AUTHORITY_"
            "TRANSACTION_DOMAIN_KEY_AND_STORE_INCARNATION"
        ),
        "security authority selector cardinality",
    )
    require_exact(
        security_profile["selector_preimage"],
        ("ABSENT_NEVER_USED_TYPED_NONMEMBERSHIP_NOT_AN_INSTALLED_PHASE"),
        "security authority selector preimage",
    )
    require_exact(
        security_profile["genesis_event"],
        "SECURITY_AUTHORITY_STATE_GENESIS_FROM_TRUST_ROOT_ENROLLMENT",
        "security authority genesis event profile",
    )
    lineage_profile = data["logical_session_generation_lineage_profile"]
    require_exact(
        lineage_profile["lineage_bootstrap"]["authority_transaction_mode"],
        "CANDIDATE_PARTICIPANT_ADMISSION",
        "source-lineage bootstrap mode",
    )
    require_exact(
        set(lineage_profile["marker_rules"]["parent_allocation_does_not_create"]),
        {
            "BODY_SESSION_CONTROL_SELECTOR",
            "SIMULATION_SESSION_STATE_SELECTOR",
            "OBSERVER_AUTHORIZATION_SELECTOR",
            "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX_SELECTOR",
        },
        "parent generation allocation precreated child selectors",
    )
    child_selector_identities = {
        (
            "installed-body-session-control-state-selector-identity::"
            "InstalledBodySessionControlStateSelector"
        ),
        (
            "installed-simulation-session-state-selector-identity::"
            "InstalledSimulationSessionStateSelector"
        ),
        (
            "installed-observer-authorization-state-selector-identity::"
            "InstalledObserverAuthorizationStateSelector"
        ),
    }
    for allocation_event_id in (
        "ALLOCATE_FIRST_LOGICAL_SESSION_GENERATION",
        "ALLOCATE_SUCCESSOR_LOGICAL_SESSION_GENERATION",
    ):
        allocation_event = events[
            ("LOGICAL_SESSION_GENERATION_LINEAGE", allocation_event_id)
        ]
        allocation_artifacts = {
            item["artifact"]
            for field in (
                "consumes",
                "creates",
                "atomic_pre_cas_payloads",
                "post_cas_sidecars",
            )
            for item in allocation_event[field]
        }
        require(
            child_selector_identities.isdisjoint(allocation_artifacts),
            (
                f"{allocation_event_id}: parent allocation precreates or "
                "consumes a child selector"
            ),
        )
        require(
            all(
                not any(
                    child_identity.split("::", 1)[1] in mutation
                    for child_identity in child_selector_identities
                )
                for mutation in allocation_event["common_case_mutates"]
            ),
            f"{allocation_event_id}: parent allocation mutates child state",
        )

    namespace_entry = domains[("LOGICAL_SESSION_NAMESPACE_REGISTRY", "NAMESPACE_ENTRY")]
    require_exact(
        set(domains[("LOGICAL_SESSION_NAMESPACE_REGISTRY", "ROOT")]["states"]),
        {
            "UNINITIALIZED",
            "OPEN_NAMESPACE",
            "DOMAIN_RETIREMENT_SEALED",
        },
        "namespace root phases",
    )
    require_exact(
        namespace_entry["key_coordinates"],
        [
            "AUTHORITY_TRANSACTION_DOMAIN_KEY",
            "SOURCE_SESSION_KIND",
            "SOURCE_LOGICAL_SESSION_ID",
        ],
        "namespace registry key",
    )
    require_exact(
        set(namespace_entry["states"]),
        {
            "ABSENT",
            "LIVE_NAMESPACE",
            "PENDING_ANCHOR_CAPACITY_RESERVATION",
            "PENDING_NAMESPACE_GENESIS",
            "PERMANENTLY_RETIRED",
        },
        "namespace entry states",
    )
    require_exact(
        event_edges(
            (
                "LOGICAL_SESSION_NAMESPACE_REGISTRY",
                "REGISTER_SOURCE_LOGICAL_SESSION_LINEAGE",
            ),
            "NAMESPACE_ENTRY",
        ),
        {("PENDING_NAMESPACE_GENESIS", "LIVE_NAMESPACE")},
        "namespace registration after protected genesis",
    )
    require_exact(
        event_edges(
            (
                "LOGICAL_SESSION_NAMESPACE_REGISTRY",
                "PREPARE_SOURCE_LOGICAL_SESSION_NAMESPACE_ANCHOR_CAPACITY_RESERVATION",
            ),
            "NAMESPACE_ENTRY",
        ),
        {("ABSENT", "PENDING_ANCHOR_CAPACITY_RESERVATION")},
        "namespace anchor-reservation preparation",
    )
    require_exact(
        event_edges(
            (
                "LOGICAL_SESSION_NAMESPACE_REGISTRY",
                "ALLOCATE_SOURCE_LOGICAL_SESSION_NAMESPACE",
            ),
            "NAMESPACE_ENTRY",
        ),
        {
            ("ABSENT", "PENDING_NAMESPACE_GENESIS"),
            (
                "PENDING_ANCHOR_CAPACITY_RESERVATION",
                "PENDING_NAMESPACE_GENESIS",
            ),
        },
        "namespace source allocation paths",
    )
    require_exact(
        event_edges(
            (
                "LOGICAL_SESSION_NAMESPACE_REGISTRY",
                "CANCEL_PENDING_SOURCE_LOGICAL_SESSION_NAMESPACE_"
                "ANCHOR_RESERVATION_INTENT",
            ),
            "NAMESPACE_ENTRY",
        ),
        {
            (
                "PENDING_ANCHOR_CAPACITY_RESERVATION",
                "PERMANENTLY_RETIRED",
            )
        },
        "namespace reservation-intent cancellation",
    )
    require_exact(
        event_edges(
            (
                "LOGICAL_SESSION_NAMESPACE_REGISTRY",
                "CANCEL_PENDING_SOURCE_LOGICAL_SESSION_NAMESPACE",
            ),
            "NAMESPACE_ENTRY",
        ),
        {("PENDING_NAMESPACE_GENESIS", "PERMANENTLY_RETIRED")},
        "namespace pending-genesis cancellation",
    )
    require_exact(
        event_edges(
            (
                "LOGICAL_SESSION_NAMESPACE_REGISTRY",
                "FINALIZE_SOURCE_LOGICAL_SESSION_PERMANENT_RETIREMENT",
            ),
            "NAMESPACE_ENTRY",
        ),
        {("LIVE_NAMESPACE", "PERMANENTLY_RETIRED")},
        "namespace permanent retirement edge",
    )
    for event_id in (
        "CANCEL_UNCONFIRMED_AUTHORITY_TRANSACTION_DOMAIN",
        "FINALIZE_AUTHORITY_TRANSACTION_DOMAIN_RETIREMENT",
    ):
        require_exact(
            event_edges(
                ("LOGICAL_SESSION_NAMESPACE_REGISTRY", event_id),
                "ROOT",
            ),
            {("OPEN_NAMESPACE", "DOMAIN_RETIREMENT_SEALED")},
            f"{event_id}: namespace root seal",
        )

    lineage_states = set(
        domains[("LOGICAL_SESSION_GENERATION_LINEAGE", "ROOT")]["states"]
    )
    require(
        {
            "SOURCE_LOGICAL_SESSION_RETIREMENT_PREPARED",
            "SOURCE_LOGICAL_SESSION_PERMANENTLY_RETIRED",
        }.issubset(lineage_states),
        "source lineage permanent-retirement states are missing",
    )
    require_exact(
        event_edges(
            (
                "LOGICAL_SESSION_GENERATION_LINEAGE",
                "PREPARE_SOURCE_LOGICAL_SESSION_PERMANENT_RETIREMENT",
            ),
            "ROOT",
        ),
        {
            (
                "NO_GENERATION",
                "SOURCE_LOGICAL_SESSION_RETIREMENT_PREPARED",
            ),
            (
                "GENERATION_FINALIZED",
                "SOURCE_LOGICAL_SESSION_RETIREMENT_PREPARED",
            ),
        },
        "source retirement preparation origins",
    )
    require_exact(
        event_edges(
            (
                "LOGICAL_SESSION_GENERATION_LINEAGE",
                "FINALIZE_SOURCE_LOGICAL_SESSION_PERMANENT_RETIREMENT",
            ),
            "ROOT",
        ),
        {
            (
                "SOURCE_LOGICAL_SESSION_RETIREMENT_PREPARED",
                "SOURCE_LOGICAL_SESSION_PERMANENTLY_RETIRED",
            )
        },
        "source permanent retirement edge",
    )
    require(
        all(
            state_edge["from_state"] != "SOURCE_LOGICAL_SESSION_PERMANENTLY_RETIRED"
            for state_edge in selectors["LOGICAL_SESSION_GENERATION_LINEAGE"][
                "state_edge_catalog"
            ]
            if state_edge["state_domain"] == "ROOT"
        ),
        "permanently retired source lineage has an exit",
    )

    target_states = set(
        domains[("OBSERVER_ATTACHMENT_TARGET_HISTORY", "TARGET_HISTORY_ENTRY")][
            "states"
        ]
    )
    require_exact(
        set(domains[("OBSERVER_ATTACHMENT_TARGET_HISTORY", "ROOT")]["states"]),
        {
            "UNINITIALIZED",
            "OPEN_TARGET_HISTORY",
            "DOMAIN_RETIREMENT_SEALED",
        },
        "target-history root phases",
    )
    require(
        {
            "SOURCE_PERMANENTLY_RETIRED_PUBLISHED_TOMBSTONE",
            "SOURCE_PERMANENTLY_RETIRED_SEALED_UNRESOLVED_TOMBSTONE",
        }.issubset(target_states),
        "target-history source-retirement tombstones are missing",
    )
    require_exact(
        event_edges(
            (
                "OBSERVER_ATTACHMENT_TARGET_HISTORY",
                "RECLAIM_SOURCE_OBSERVER_TARGET_HISTORY_DURING_PERMANENT_RETIREMENT",
            ),
            "TARGET_HISTORY_ENTRY",
        ),
        {
            (
                "CHECKPOINT_PUBLISHED",
                "SOURCE_PERMANENTLY_RETIRED_PUBLISHED_TOMBSTONE",
            ),
            (
                "SOURCE_GENERATION_FINALIZED_PENDING_CHECKPOINT_PUBLICATION",
                "SOURCE_PERMANENTLY_RETIRED_SEALED_UNRESOLVED_TOMBSTONE",
            ),
        },
        "target-history source-retirement projection",
    )

    quarantine = domains[("OBSERVER_UNRESOLVED_TARGET_QUARANTINE", "QUARANTINE_ENTRY")]
    require_exact(
        set(domains[("OBSERVER_UNRESOLVED_TARGET_QUARANTINE", "ROOT")]["states"]),
        {
            "UNINITIALIZED",
            "OPEN_QUARANTINE",
            "DOMAIN_RETIREMENT_SEALED",
        },
        "quarantine root phases",
    )
    require_exact(
        set(quarantine["states"]),
        {
            "ABSENT",
            "SEALED_UNRESOLVED",
            "ARCHIVED_NONAUTHORIZING_TOMBSTONE",
        },
        "observer quarantine states",
    )
    require_exact(
        event_edges(
            (
                "OBSERVER_UNRESOLVED_TARGET_QUARANTINE",
                "SEAL_UNRESOLVED_OBSERVER_TARGETS",
            ),
            "QUARANTINE_ENTRY",
        ),
        {("ABSENT", "SEALED_UNRESOLVED")},
        "observer quarantine seal edge",
    )
    require_exact(
        event_edges(
            (
                "OBSERVER_UNRESOLVED_TARGET_QUARANTINE",
                "ARCHIVE_AND_RECLAIM_OBSERVER_QUARANTINE_ENTRY",
            ),
            "QUARANTINE_ENTRY",
        ),
        {
            (
                "SEALED_UNRESOLVED",
                "ARCHIVED_NONAUTHORIZING_TOMBSTONE",
            )
        },
        "observer quarantine archive edge",
    )
    for selector_id, open_state in (
        ("OBSERVER_ATTACHMENT_TARGET_HISTORY", "OPEN_TARGET_HISTORY"),
        ("OBSERVER_UNRESOLVED_TARGET_QUARANTINE", "OPEN_QUARANTINE"),
    ):
        for event_id in (
            "CANCEL_UNCONFIRMED_AUTHORITY_TRANSACTION_DOMAIN",
            "FINALIZE_AUTHORITY_TRANSACTION_DOMAIN_RETIREMENT",
        ):
            require_exact(
                event_edges((selector_id, event_id), "ROOT"),
                {(open_state, "DOMAIN_RETIREMENT_SEALED")},
                f"{selector_id}.{event_id}: core root seal",
            )
    require(
        all(
            event_id != "RECORD_QUARANTINED_OBSERVER_TARGET_LATE_CLOSURE"
            for _, event_id in events
        ),
        "archive-only late closure must not mutate a selector",
    )
    late_closure = data["observer_unresolved_target_quarantine_profile"][
        "late_closure_external_event"
    ]
    require_exact(
        late_closure["effect"],
        "ARCHIVE_ENRICHMENT_ONLY_NO_AUTHORITY",
        "late quarantine closure effect",
    )
    require_exact(
        late_closure["selector_mutation"],
        False,
        "late quarantine selector mutation",
    )
    require_exact(
        late_closure["authority_transaction_domain_operation"],
        False,
        "late quarantine domain operation",
    )

    physical_selector_id = "PHYSICAL_ACTUATION_JURISDICTION_ENROLLMENT_REGISTRY"
    physical_root = domains[(physical_selector_id, "ROOT")]
    require_exact(
        set(physical_root["states"]),
        {
            "ABSENT_NEVER_USED",
            "ACTIVE_FACILITY_REGISTRY",
            "RETIREMENT_DRAIN_ONLY",
            "PERMANENTLY_RETIRED",
        },
        "facility registry root states",
    )
    require_exact(
        physical_root["absence_semantics"],
        "EXACT_SELECTOR_ABSENCE_WITH_NEVER_REUSE_TOMBSTONE",
        "facility registry selector absence semantics",
    )
    physical_slot = domains[(physical_selector_id, "JURISDICTION_ENROLLMENT_SLOT")]
    require_exact(
        physical_slot["key_coordinates"],
        [
            "PHYSICAL_ACTUATION_FACILITY_KEY",
            "PHYSICAL_ACTUATION_JURISDICTION_ENROLLMENT_SLOT_KEY",
        ],
        "facility slot key",
    )
    require_exact(
        set(physical_slot["states"]),
        {
            "ABSENT",
            "UNASSIGNED_PHYSICALLY_ISOLATED",
            "RESERVATION_PREPARED_NO_REALM_AUTHORITY",
            "RESERVATION_INSTALLATION_INVALIDATION_PREPARED",
            "RESERVED_FOR_AUTHORITY_REALM_FENCED",
            "RESERVED_EPOCH_INVALIDATION_PREPARED",
            "INSTALLED_FOR_AUTHORITY_REALM_FENCED",
            "INSTALLED_EPOCH_INVALIDATION_PREPARED",
            "HANDOVER_FENCED",
            "HARDWARE_RETIRED",
        },
        "facility slot-owner states",
    )
    path_epoch_ledger = domains[(physical_selector_id, "PATH_EPOCH_TOMBSTONE_LEDGER")]
    require_exact(
        path_epoch_ledger["key_coordinates"],
        [
            "PHYSICAL_ACTUATION_FACILITY_KEY",
            "PHYSICAL_EFFECT_PATH_KEY",
            "FENCING_EPOCH",
        ],
        "facility path-epoch tombstone key",
    )
    require_exact(
        set(path_epoch_ledger["states"]),
        {"ABSENT", "ISSUED", "ELIMINATED_TOMBSTONE"},
        "facility path-epoch tombstone states",
    )
    require_exact(
        domains[(physical_selector_id, "FENCING_EPOCH_NO_REUSE")]["key_coordinates"],
        [
            "PHYSICAL_ACTUATION_FACILITY_KEY",
            "PHYSICAL_ACTUATION_JURISDICTION_ENROLLMENT_SLOT_KEY",
            "FENCING_EPOCH",
        ],
        "facility fencing-epoch key",
    )
    physical_profile = data["physical_actuation_jurisdiction_enrollment_profile"]
    physical_events = {
        event["event_id"] for event in selectors[physical_selector_id]["events"]
    }
    require_exact(
        physical_events,
        set(physical_profile["closed_selector_event_surface"]),
        "facility closed event surface",
    )
    require_exact(
        physical_events,
        {
            (
                "PHYSICAL_ACTUATION_JURISDICTION_ENROLLMENT_REGISTRY_"
                "GENESIS_FROM_FACILITY_AUTHORITY"
            ),
            ("PREPARE_PHYSICAL_ACTUATION_JURISDICTION_RESERVATION_FOR_AUTHORITY_REALM"),
            (
                "CONFIRM_PHYSICAL_ACTUATION_JURISDICTION_RESERVATION_AFTER_"
                "HARDWARE_FENCE"
            ),
            (
                "RETIRE_PREPARED_PHYSICAL_ACTUATION_JURISDICTION_AFTER_"
                "EPOCH_INVALIDATION"
            ),
            "CONFIRM_PHYSICAL_ACTUATION_JURISDICTION_ENROLLMENT",
            "PREPARE_PHYSICAL_ACTUATION_JURISDICTION_EPOCH_INVALIDATION",
            (
                "ABANDON_RESERVED_PHYSICAL_ACTUATION_JURISDICTION_AFTER_"
                "EPOCH_INVALIDATION"
            ),
            "BEGIN_PHYSICAL_ACTUATION_JURISDICTION_HANDOVER",
            "RELEASE_PHYSICAL_ACTUATION_JURISDICTION_AFTER_ISOLATION",
            "RETIRE_PHYSICAL_ACTUATION_JURISDICTION_HARDWARE",
            "BEGIN_PHYSICAL_ACTUATION_FACILITY_REGISTRY_RETIREMENT",
            "FINALIZE_PHYSICAL_ACTUATION_FACILITY_REGISTRY_RETIREMENT",
        },
        "facility exact event surface",
    )
    for external_event in (
        "INSTALL_PHYSICAL_ACTUATION_JURISDICTION_FENCING_EPOCH",
        "INVALIDATE_PHYSICAL_ACTUATION_JURISDICTION_EPOCH_AND_ISOLATE",
    ):
        require(
            all(event_id != external_event for _, event_id in events),
            f"{external_event}: hardware effect modeled as selector event",
        )
    require_exact(
        physical_profile["realm_authority_transaction_participant"],
        False,
        "facility realm transaction participation",
    )
    require_exact(
        physical_profile["live_cross_provider_qualification_status"],
        "NOT_RUN",
        "facility live qualification status",
    )
    hardware_profile = data["physical_actuation_jurisdiction_hardware_epoch_profile"]
    require_exact(
        hardware_profile["storage_atomicity_claim"],
        "FORBIDDEN",
        "hardware storage atomicity claim",
    )
    require_exact(
        hardware_profile["hardware_qualification_status"],
        "NOT_RUN",
        "hardware qualification status",
    )
    require_exact(
        set(physical_profile["registry_states"]),
        {
            "ACTIVE_FACILITY_REGISTRY",
            "RETIREMENT_DRAIN_ONLY",
            "PERMANENTLY_RETIRED",
        },
        "facility profile registry states",
    )
    slot_admission_profile = physical_profile["slot_realm_admission_evidence"]
    slot_admission_type = (
        "physical-actuation-slot-realm-admission-evidence-type::"
        "PhysicalActuationSlotRealmAdmissionEvidence"
    )
    slot_admission_variants = {
        "NEVER_ASSIGNED_SLOT",
        "SAME_AUTHORITY_REALM_REENROLLMENT",
        "PRIOR_AUTHORITY_REALM_PERMANENTLY_RETIRED",
    }
    require_exact(
        slot_admission_profile["type"],
        slot_admission_type,
        "facility slot realm-admission evidence type",
    )
    require_exact(
        set(slot_admission_profile["variants"]),
        slot_admission_variants,
        "facility slot realm-admission evidence closure",
    )
    require_exact(
        slot_admission_profile["unassigned_prior_realm_barrier"],
        (
            "TYPED_ABSENT_ONLY_BEFORE_FIRST_ASSIGNMENT_THEN_RETAINED_"
            "IMMUTABLY_ACROSS_LOCAL_RELEASE"
        ),
        "facility retained prior-realm barrier",
    )
    require_exact(
        slot_admission_profile["same_realm_requirement"],
        (
            "EXACT_RETAINED_PRIOR_REALM_EQUALS_TARGET_AND_EXACT_LOCAL_"
            "ISOLATION_RELEASE_RECEIPT"
        ),
        "facility same-realm admission requirement",
    )
    require_exact(
        slot_admission_profile["different_realm_requirement"],
        (
            "EXACT_PRIOR_HIGHER_ROOT_PERMANENT_REALM_TOMBSTONE_PRECEDES_"
            "NEW_FENCING_EPOCH_ALLOCATION"
        ),
        "facility different-realm admission requirement",
    )
    require_exact(
        slot_admission_profile["anti_overlap_effect"],
        (
            "OLD_REALM_ISOLATION_ENVELOPE_CANNOT_LATER_NAME_OR_CUT_NEW_"
            "REALM_HARDWARE_EPOCH_TOKEN_OR_IDENTITY"
        ),
        "facility cross-realm anti-overlap effect",
    )
    require_exact(
        slot_admission_profile["unknown_default_missing_or_mixed_variant"],
        "REJECT",
        "facility unknown slot realm-admission evidence",
    )
    require_exact(
        physical_profile["transaction_contract"][
            "strict_serializable_one_selector_cas"
        ],
        True,
        "facility storage CAS qualification",
    )
    require_exact(
        physical_profile["transaction_contract"]["hardware_is_part_of_storage_cas"],
        False,
        "facility hardware/storage atomicity separation",
    )
    require_exact(
        set(physical_profile["hardware_epoch_elimination_evidence"]["variants"]),
        {
            "EXACT_HARDWARE_INVALIDATION_RECEIPT",
            ("LOST_HARDWARE_STATE_COMPLETE_COMPONENT_ISOLATED_IDENTITIES_RETIRED"),
        },
        "facility hardware elimination evidence",
    )
    facility_retirement_causes = {
        "CAPACITY_THRESHOLD",
        "ADMINISTRATIVE_FACILITY_RETIREMENT",
        ("ACTIVE_QUALIFICATION_WITHDRAWN_RESTRICTIVE_CLOSE_STILL_QUALIFIED"),
    }
    require_exact(
        set(physical_profile["facility_retirement_cause"]["variants"]),
        facility_retirement_causes,
        "facility retirement causes",
    )

    facility_commit_receipt = (
        "physical-actuation-facility-commit-receipt-type::"
        "PhysicalActuationFacilityCommitReceipt"
    )
    facility_cas_condition = (
        "physical-actuation-facility-cas-condition-type::"
        "PhysicalActuationFacilityCASCondition"
    )
    facility_manifest = (
        "physical-actuation-facility-persistence-manifest-type::"
        "PhysicalActuationFacilityPersistenceManifest"
    )
    facility_qualification_receipt = (
        "physical-actuation-facility-registry-qualification-receipt-type::"
        "PhysicalActuationFacilityRegistryQualificationReceipt"
    )
    require_exact(
        selectors[physical_selector_id]["generic_receipt"],
        facility_commit_receipt,
        "facility generic commit receipt",
    )
    candidate_constraint_profiles = {
        item["profile_id"]: item["value"]
        for item in data["closed_event_profile_catalog"]["candidate_constraints"]
    }
    facility_genesis_id = (
        "PHYSICAL_ACTUATION_JURISDICTION_ENROLLMENT_REGISTRY_"
        "GENESIS_FROM_FACILITY_AUTHORITY"
    )
    for physical_event in selectors[physical_selector_id]["events"]:
        event_id = physical_event["event_id"]
        contract = physical_event["physical_facility_registry_contract"]
        require_exact(
            contract["commit_receipt"],
            facility_commit_receipt,
            f"{event_id}: facility commit receipt",
        )
        require_exact(
            contract["persistence_manifest"],
            facility_manifest,
            f"{event_id}: facility persistence manifest",
        )
        require(
            facility_qualification_receipt
            in {item["artifact"] for item in physical_event["consumes"]},
            f"{event_id}: missing facility qualification receipt",
        )
        sidecar_dependencies = {
            item["artifact"]: set(item["depends_on"])
            for item in physical_event["post_cas_sidecars"]
        }
        require_exact(
            sidecar_dependencies[facility_manifest],
            set(sidecar_dependencies) - {facility_manifest},
            f"{event_id}: facility manifest dependency closure",
        )
        facility_cas_payloads = [
            item
            for item in physical_event["atomic_pre_cas_payloads"]
            if item["artifact"] == facility_cas_condition
        ]
        require_exact(
            len(facility_cas_payloads),
            0 if event_id == facility_genesis_id else 1,
            f"{event_id}: facility CAS payload count",
        )
        require(
            "PHYSICAL_ACTUATION_FACILITY_COMMIT_RECEIPT"
            in candidate_constraint_profiles[
                physical_event["candidate_constraints_profile_ref"]
            ]["excludes"],
            f"{event_id}: facility candidate can bind its commit receipt",
        )

    facility_genesis = events[(physical_selector_id, facility_genesis_id)]
    require_exact(
        facility_genesis["pre_cas_content"]["artifact"],
        (
            "physical-actuation-facility-registry-genesis-fact-type::"
            "PhysicalActuationFacilityRegistryGenesisFact"
        ),
        "facility genesis fact",
    )
    require_exact(
        event_edges(
            (physical_selector_id, facility_genesis_id),
            "ROOT",
        ),
        {("ABSENT_NEVER_USED", "ACTIVE_FACILITY_REGISTRY")},
        "facility genesis root edge",
    )
    genesis_slot_partition = partition_for(
        (physical_selector_id, facility_genesis_id),
        "JURISDICTION_ENROLLMENT_SLOT",
    )
    require_exact(
        {
            (
                branch["from_state"],
                branch["to_state"],
                branch["cardinality"],
            )
            for branch in genesis_slot_partition["branches"]
        },
        {
            (
                "ABSENT",
                "UNASSIGNED_PHYSICALLY_ISOLATED",
                "ONE_OR_MORE_BOUNDED_CANONICALLY_ORDERED_SLOT_KEYS",
            )
        },
        "facility genesis slot inventory",
    )

    prepare_reservation = events[
        (
            physical_selector_id,
            "PREPARE_PHYSICAL_ACTUATION_JURISDICTION_RESERVATION_FOR_AUTHORITY_REALM",
        )
    ]
    require_exact(
        {case["semantic_case_id"] for case in prepare_reservation["transition_cases"]},
        slot_admission_variants,
        "facility prepare slot realm-admission semantic closure",
    )
    slot_admission_contract = prepare_reservation["slot_realm_admission_contract"]
    require_exact(
        slot_admission_contract["evidence_type"],
        slot_admission_type,
        "facility prepare slot realm-admission evidence",
    )
    require_exact(
        set(slot_admission_contract["closed_variants"]),
        slot_admission_variants,
        "facility prepare slot realm-admission variants",
    )
    require_exact(
        slot_admission_contract["unknown_default_missing_or_mixed_variant"],
        "REJECT",
        "facility prepare unknown realm-admission branch",
    )
    prepare_consumes = {
        (
            item["artifact"],
            item.get("branch_condition"),
        )
        for item in prepare_reservation["consumes"]
    }
    require(
        (slot_admission_type, None) in prepare_consumes,
        "facility prepare lacks closed slot realm-admission evidence",
    )
    require(
        (
            (
                "physical-actuation-jurisdiction-isolation-release-receipt-"
                "type::PhysicalActuationJurisdictionIsolationReleaseReceipt"
            ),
            "SAME_AUTHORITY_REALM_REENROLLMENT",
        )
        in prepare_consumes,
        "same-realm re-enrollment lacks exact local isolation release",
    )
    require(
        (
            (
                "authority-realm-enrollment-retirement-evidence-type::"
                "AuthorityRealmEnrollmentRetirementEvidence"
            ),
            "PRIOR_AUTHORITY_REALM_PERMANENTLY_RETIRED",
        )
        in prepare_consumes,
        "different-realm admission lacks exact higher-root tombstone",
    )
    for binding in (
        "UNASSIGNED_SLOT_RETAINS_PRIOR_REALM_BARRIER_AFTER_FIRST_ASSIGNMENT",
        (
            "DIFFERENT_REALM_BRANCH_REQUIRES_EXACT_PRIOR_HIGHER_ROOT_"
            "PERMANENT_REALM_TOMBSTONE"
        ),
        (
            "OLD_REALM_ISOLATION_ENVELOPE_CANNOT_TARGET_NEW_REALM_EPOCH_"
            "TOKEN_OR_HARDWARE_IDENTITY"
        ),
    ):
        require(
            binding in prepare_reservation["pre_cas_content"]["required_bindings"],
            f"facility prepare lacks anti-overlap binding {binding}",
        )
    prepare_sidecars = {
        item["artifact"]: item for item in prepare_reservation["post_cas_sidecars"]
    }
    install_authorization = (
        "physical-actuation-jurisdiction-hardware-fence-installation-"
        "authorization-type::"
        "PhysicalActuationJurisdictionHardwareFenceInstallationAuthorization"
    )
    require(
        install_authorization in prepare_sidecars,
        "facility prepare lacks hardware-install authorization",
    )
    require_exact(
        prepare_sidecars[install_authorization]["artifact_class"],
        "SIGNED_POST_CAS_ONE_USE_HARDWARE_AUTHORIZATION",
        "facility hardware-install authorization class",
    )
    require(
        "CANDIDATE_SELECTOR_OR_HEAD_AS_AUTHORITY"
        in prepare_sidecars[install_authorization]["forbidden_bindings"],
        "facility candidate can drive hardware install",
    )
    confirm_reservation = events[
        (
            physical_selector_id,
            "CONFIRM_PHYSICAL_ACTUATION_JURISDICTION_RESERVATION_AFTER_HARDWARE_FENCE",
        )
    ]
    require(
        (
            "physical-actuation-jurisdiction-hardware-fence-installation-"
            "receipt-type::"
            "PhysicalActuationJurisdictionHardwareFenceInstallationReceipt"
        )
        in {item["artifact"] for item in confirm_reservation["consumes"]},
        "facility reservation confirmation lacks hardware receipt",
    )
    require_exact(
        event_edges(
            (
                physical_selector_id,
                "CONFIRM_PHYSICAL_ACTUATION_JURISDICTION_RESERVATION_AFTER_"
                "HARDWARE_FENCE",
            ),
            "JURISDICTION_ENROLLMENT_SLOT",
        ),
        {
            (
                "RESERVATION_PREPARED_NO_REALM_AUTHORITY",
                "RESERVED_FOR_AUTHORITY_REALM_FENCED",
            )
        },
        "facility hardware-confirmation edge",
    )
    prepare_invalidation = events[
        (
            physical_selector_id,
            "PREPARE_PHYSICAL_ACTUATION_JURISDICTION_EPOCH_INVALIDATION",
        )
    ]
    require_exact(
        event_edges(
            (
                physical_selector_id,
                "PREPARE_PHYSICAL_ACTUATION_JURISDICTION_EPOCH_INVALIDATION",
            ),
            "JURISDICTION_ENROLLMENT_SLOT",
        ),
        {
            (
                "RESERVATION_PREPARED_NO_REALM_AUTHORITY",
                "RESERVATION_INSTALLATION_INVALIDATION_PREPARED",
            ),
            (
                "RESERVED_FOR_AUTHORITY_REALM_FENCED",
                "RESERVED_EPOCH_INVALIDATION_PREPARED",
            ),
            (
                "INSTALLED_FOR_AUTHORITY_REALM_FENCED",
                "INSTALLED_EPOCH_INVALIDATION_PREPARED",
            ),
        },
        "facility invalidation preparation edges",
    )
    invalidation_authorization = (
        "physical-actuation-jurisdiction-hardware-epoch-invalidation-"
        "authorization-type::"
        "PhysicalActuationJurisdictionHardwareEpochInvalidationAuthorization"
    )
    invalidation_sidecar = next(
        (
            item
            for item in prepare_invalidation["post_cas_sidecars"]
            if item["artifact"] == invalidation_authorization
        ),
        None,
    )
    require(
        invalidation_sidecar is not None,
        "facility invalidation prepare lacks hardware authorization",
    )
    require_exact(
        invalidation_sidecar["artifact_class"],
        "SIGNED_POST_CAS_ONE_USE_HARDWARE_AUTHORIZATION",
        "facility invalidation authorization class",
    )
    for binding in (
        "EXACT_ORIGINAL_INSTALLATION_TOKEN",
        "INSTALLATION_AND_INVALIDATION_SAME_TOKEN_SERIALIZATION_RULE",
        "DURABLE_INSTALLATION_INVALIDATION_TOKEN_AND_EPOCH_TOMBSTONE_INTENT",
    ):
        require(
            binding in invalidation_sidecar["additional_bindings"],
            f"facility invalidation authorization lacks {binding}",
        )

    elimination_variants = {
        "EXACT_HARDWARE_INVALIDATION_RECEIPT",
        ("LOST_HARDWARE_STATE_COMPLETE_COMPONENT_ISOLATED_IDENTITIES_RETIRED"),
    }
    facility_root_variants = {
        "ACTIVE_FACILITY_REGISTRY",
        "RETIREMENT_DRAIN_ONLY",
    }
    prepared_retirement_id = (
        "RETIRE_PREPARED_PHYSICAL_ACTUATION_JURISDICTION_AFTER_EPOCH_INVALIDATION"
    )
    prepared_retirement = events[(physical_selector_id, prepared_retirement_id)]
    require_exact(
        {case["semantic_case_id"] for case in prepared_retirement["transition_cases"]},
        {
            f"{root_state}__{elimination}"
            for root_state in facility_root_variants
            for elimination in elimination_variants
        },
        "prepared installation invalidation closure",
    )
    require_exact(
        event_edges(
            (physical_selector_id, prepared_retirement_id),
            "JURISDICTION_ENROLLMENT_SLOT",
        ),
        {
            (
                "RESERVATION_INSTALLATION_INVALIDATION_PREPARED",
                "UNASSIGNED_PHYSICALLY_ISOLATED",
            ),
            (
                "RESERVATION_INSTALLATION_INVALIDATION_PREPARED",
                "HARDWARE_RETIRED",
            ),
        },
        "prepared installation invalidation outcome edges",
    )
    for evidence_artifact, branch_condition in (
        (
            (
                "physical-actuation-jurisdiction-hardware-epoch-"
                "invalidation-receipt-type::"
                "PhysicalActuationJurisdictionHardwareEpochInvalidationReceipt"
            ),
            "EXACT_HARDWARE_INVALIDATION_RECEIPT",
        ),
        (
            (
                "physical-actuation-lost-hardware-state-isolation-fact-type::"
                "PhysicalActuationLostHardwareStateIsolationFact"
            ),
            ("LOST_HARDWARE_STATE_COMPLETE_COMPONENT_ISOLATED_IDENTITIES_RETIRED"),
        ),
    ):
        require(
            any(
                item["artifact"] == evidence_artifact
                and item["branch_condition"] == branch_condition
                for item in prepared_retirement["consumes"]
            ),
            (f"{prepared_retirement_id}: missing branch evidence {evidence_artifact}"),
        )

    abandonment_id = (
        "ABANDON_RESERVED_PHYSICAL_ACTUATION_JURISDICTION_AFTER_EPOCH_INVALIDATION"
    )
    abandonment_variants = {
        "NO_LOCAL_REGISTRY_GENESIS_CANCELED",
        "UNCONFIRMED_LOCAL_REGISTRY_RETIRED",
        "TARGET_REALM_STATE_LOST_PERMANENTLY_ISOLATED",
    }
    handover_id = "BEGIN_PHYSICAL_ACTUATION_JURISDICTION_HANDOVER"
    handover_variants = {
        "EXACT_ACTIVE_LOCAL_JURISDICTION_RETIREMENT",
        ("UNCONFIRMED_EMPTY_LOCAL_REGISTRY_RETIRED_AFTER_LATE_FACILITY_CONFIRMATION"),
        "LOST_REALM_STATE_PERMANENTLY_ISOLATED",
    }
    for event_id, evidence_variants, source_state, exact_target in (
        (
            abandonment_id,
            abandonment_variants,
            "RESERVED_EPOCH_INVALIDATION_PREPARED",
            "UNASSIGNED_PHYSICALLY_ISOLATED",
        ),
        (
            handover_id,
            handover_variants,
            "INSTALLED_EPOCH_INVALIDATION_PREPARED",
            "HANDOVER_FENCED",
        ),
    ):
        physical_event = events[(physical_selector_id, event_id)]
        require_exact(
            {case["semantic_case_id"] for case in physical_event["transition_cases"]},
            {
                f"{root_state}__{evidence}__{elimination}"
                for root_state in facility_root_variants
                for evidence in evidence_variants
                for elimination in elimination_variants
            },
            f"{event_id}: evidence closure",
        )
        require_exact(
            event_edges(
                (physical_selector_id, event_id),
                "JURISDICTION_ENROLLMENT_SLOT",
            ),
            {
                (source_state, exact_target),
                (source_state, "HARDWARE_RETIRED"),
            },
            f"{event_id}: hardware elimination outcome edges",
        )
        require(
            (
                "physical-actuation-hardware-epoch-elimination-evidence-"
                "type::PhysicalActuationHardwareEpochEliminationEvidence"
            )
            in {item["artifact"] for item in physical_event["consumes"]},
            f"{event_id}: missing closed hardware elimination evidence",
        )
        require(
            any(
                item["artifact"]
                == (
                    "physical-actuation-lost-hardware-state-isolation-"
                    "fact-type::"
                    "PhysicalActuationLostHardwareStateIsolationFact"
                )
                and item["branch_condition"]
                == (
                    "LOST_HARDWARE_STATE_COMPLETE_COMPONENT_ISOLATED_IDENTITIES_RETIRED"
                )
                for item in physical_event["consumes"]
            ),
            f"{event_id}: lost hardware branch lacks isolation fact",
        )

    facility_begin_id = "BEGIN_PHYSICAL_ACTUATION_FACILITY_REGISTRY_RETIREMENT"
    facility_final_id = "FINALIZE_PHYSICAL_ACTUATION_FACILITY_REGISTRY_RETIREMENT"
    require_exact(
        event_edges((physical_selector_id, facility_begin_id), "ROOT"),
        {("ACTIVE_FACILITY_REGISTRY", "RETIREMENT_DRAIN_ONLY")},
        "facility retirement begin edge",
    )
    require_exact(
        {
            case["semantic_case_id"]
            for case in events[(physical_selector_id, facility_begin_id)][
                "transition_cases"
            ]
        },
        facility_retirement_causes,
        "facility retirement cause closure",
    )
    require_exact(
        event_edges((physical_selector_id, facility_final_id), "ROOT"),
        {("RETIREMENT_DRAIN_ONLY", "PERMANENTLY_RETIRED")},
        "facility retirement final edge",
    )
    final_slots = partition_for(
        (physical_selector_id, facility_final_id),
        "JURISDICTION_ENROLLMENT_SLOT",
    )
    require_exact(
        {
            (branch["from_state"], branch["to_state"])
            for branch in final_slots["branches"]
        },
        {("HARDWARE_RETIRED", "HARDWARE_RETIRED")},
        "facility final all-slot proof",
    )
    final_epochs = partition_for(
        (physical_selector_id, facility_final_id),
        "FENCING_EPOCH_NO_REUSE",
    )
    require_exact(
        {
            (branch["from_state"], branch["to_state"])
            for branch in final_epochs["branches"]
        },
        {("INVALIDATED_TOMBSTONE", "INVALIDATED_TOMBSTONE")},
        "facility final epoch proof",
    )

    arbiter_root_states = set(domains[("ACTUATION_AUTHORITY_DOMAIN", "ROOT")]["states"])
    require(
        "PENDING_FACILITY_CONFIRMATION" in arbiter_root_states,
        "local jurisdiction registry lacks pending facility state",
    )
    require_exact(
        event_edges(
            (
                "ACTUATION_AUTHORITY_DOMAIN",
                "ACTUATION_AUTHORITY_DOMAIN_REGISTRY_GENESIS_FROM_"
                "PHYSICAL_JURISDICTION_ENROLLMENT",
            ),
            "ROOT",
        ),
        {("ABSENT_NEVER_USED", "PENDING_FACILITY_CONFIRMATION")},
        "local jurisdiction genesis pending edge",
    )
    actuation_pre_genesis_cancel = events[
        (
            "ACTUATION_AUTHORITY_DOMAIN",
            "CANCEL_ACTUATION_AUTHORITY_DOMAIN_REGISTRY_GENESIS_BEFORE_CREATION",
        )
    ]
    require_exact(
        actuation_pre_genesis_cancel["authority_transaction_contract"][
            "participant_set_mode"
        ],
        "PRE_GENESIS_TOMBSTONE_INSTALLATION",
        "actuation pre-genesis cancellation mode",
    )
    require_exact(
        actuation_pre_genesis_cancel["authority_transaction_contract"]["domain_state"],
        "ACTIVE",
        "actuation pre-genesis cancellation domain state",
    )
    require(
        "fresh_native_participant_admission_contract"
        not in actuation_pre_genesis_cancel,
        "actuation pre-genesis cancellation claims participant admission",
    )
    pre_genesis_tombstone_contract = actuation_pre_genesis_cancel[
        "pre_genesis_tombstone_installation_contract"
    ]
    require_exact(
        pre_genesis_tombstone_contract["participant_admission"],
        "FORBIDDEN",
        "actuation pre-genesis cancellation participant admission",
    )
    require_exact(
        pre_genesis_tombstone_contract["native_genesis_receipt"],
        "FORBIDDEN",
        "actuation pre-genesis cancellation native genesis receipt",
    )
    require_exact(
        pre_genesis_tombstone_contract["one_use_authorization"],
        (
            "physical-actuation-jurisdiction-enrollment-reservation-receipt-"
            "type::PhysicalActuationJurisdictionEnrollmentReservationReceipt"
        ),
        "actuation pre-genesis cancellation authorization",
    )
    require(
        {
            "PRIOR_ROOT_ABSENCE_AND_NEVER_USED_NONMEMBERSHIP",
            "EXACT_TYPED_NEVER_USED_TARGET_SELECTOR_KEY_NONMEMBERSHIP",
            "ATOMIC_TERMINAL_TOMBSTONE_AND_IDENTITY_NO_REUSE_INSTALL",
            "NO_PARTICIPANT_ENTRY_ACL_OR_AUTHORITY_INSTALL",
        }.issubset(
            set(actuation_pre_genesis_cancel["pre_cas_content"]["required_bindings"])
        ),
        "actuation pre-genesis cancellation closure bindings",
    )
    pre_genesis_cancel_sidecars = {
        item["artifact"] for item in actuation_pre_genesis_cancel["post_cas_sidecars"]
    }
    require(
        (
            "actuation-authority-domain-registry-genesis-cancellation-"
            "receipt-type::"
            "ActuationAuthorityDomainRegistryGenesisCancellationReceipt"
        )
        in pre_genesis_cancel_sidecars,
        "actuation pre-genesis cancellation receipt missing",
    )
    require(
        native_genesis_receipt not in pre_genesis_cancel_sidecars
        and participant_admission_receipt not in pre_genesis_cancel_sidecars,
        "actuation pre-genesis cancellation emits admission receipts",
    )
    require_exact(
        event_edges(
            (
                "ACTUATION_AUTHORITY_DOMAIN",
                "ACTIVATE_ACTUATION_AUTHORITY_DOMAIN_REGISTRY_AFTER_"
                "FACILITY_CONFIRMATION",
            ),
            "ROOT",
        ),
        {("PENDING_FACILITY_CONFIRMATION", "ACTIVE_REGISTRY")},
        "local jurisdiction facility activation edge",
    )
    reserve_root_edges = event_edges(
        (
            "ACTUATION_AUTHORITY_DOMAIN",
            "RESERVE_ACTUATION_AUTHORITY_DOMAIN_FOR_GENERATION",
        ),
        "ROOT",
    )
    require(
        all(
            source != "PENDING_FACILITY_CONFIRMATION"
            for source, _ in reserve_root_edges
        ),
        "pending facility registry can reserve an actuation domain",
    )

    domain_contract_exempt_events = {
        (
            "AUTHORITY_TRANSACTION_DOMAIN",
            "CANCEL_AUTHORITY_TRANSACTION_DOMAIN_GENESIS_BEFORE_CREATION",
        ),
    }
    arbiter_facility_lifecycle_events = {
        "ACTUATION_AUTHORITY_DOMAIN_REGISTRY_GENESIS_FROM_"
        "PHYSICAL_JURISDICTION_ENROLLMENT",
        "ACTIVATE_ACTUATION_AUTHORITY_DOMAIN_REGISTRY_AFTER_FACILITY_CONFIRMATION",
        "CANCEL_ACTUATION_AUTHORITY_DOMAIN_REGISTRY_GENESIS_BEFORE_CREATION",
        "RETIRE_UNCONFIRMED_ACTUATION_AUTHORITY_DOMAIN_REGISTRY",
    }
    for selector_id, primary_role in authority_selector_roles.items():
        event_closed_roles = (
            independent_anchor_closed_roles
            if selector_id in independent_anchor_selectors
            else closed_roles
        )
        for event in selectors[selector_id]["events"]:
            label = f"{selector_id}.{event['event_id']}"
            expected_event_roles = restricted_role_universe_by_event.get(
                (selector_id, event["event_id"]),
                event_closed_roles,
            )
            if (selector_id, event["event_id"]) in (domain_contract_exempt_events):
                require(
                    "authority_transaction_contract" not in event,
                    f"{label}: bootstrap cancellation claims absent domain",
                )
                continue
            contract = event.get("authority_transaction_contract")
            require(contract is not None, f"{label}: missing domain contract")
            require_unique(
                contract["role_universe"],
                f"{label}: role universe",
            )
            require_unique(
                contract["write_roles"],
                f"{label}: contract write roles",
            )
            require_exact(
                set(contract["role_universe"]),
                expected_event_roles,
                f"{label}: role universe",
            )
            require(
                set(contract["write_roles"]).issubset(expected_event_roles),
                f"{label}: contract contains an unknown write role",
            )
            require(
                "AUTHORITY_TRANSACTION_DOMAIN_STATE" in contract["write_roles"],
                f"{label}: domain-state participant is not written",
            )
            require(
                primary_role in contract["write_roles"]
                or contract["participant_set_mode"]
                in {
                    "DOMAIN_STATE_PLUS_EXACT_QUALIFIED_TARGET_PARTICIPANT",
                    "CANONICAL_COMPLETE_APPLICABLE_SUBSET_FROM_LIVE_PARTICIPANT_REGISTRY",
                },
                f"{label}: primary selector is not an authorized writer",
            )
            case_write_roles = contract.get("write_roles_by_semantic_case")
            if case_write_roles is not None:
                require(
                    isinstance(case_write_roles, dict),
                    f"{label}: case-specific write roles must be an object",
                )
                case_ids = {
                    case["semantic_case_id"] for case in event["transition_cases"]
                }
                require_exact(
                    set(case_write_roles),
                    case_ids,
                    f"{label}: case-specific write-role coverage",
                )
                union_case_writes: set[str] = set()
                for case_id, roles in case_write_roles.items():
                    require(
                        isinstance(roles, list),
                        f"{label}.{case_id}: write roles must be an array",
                    )
                    require_unique(
                        roles,
                        f"{label}.{case_id}: write roles",
                    )
                    require(
                        set(roles).issubset(expected_event_roles),
                        f"{label}.{case_id}: unknown write role",
                    )
                    require(
                        {
                            "AUTHORITY_TRANSACTION_DOMAIN_STATE",
                            primary_role,
                        }.issubset(roles),
                        (
                            f"{label}.{case_id}: domain state or primary "
                            "selector is not written"
                        ),
                    )
                    union_case_writes.update(roles)
                require_exact(
                    union_case_writes,
                    set(contract["write_roles"]),
                    f"{label}: case-specific write-role union",
                )
            participant_variants = contract["participant_role_variants"]
            for variant in participant_variants:
                roles = variant["participant_roles"]
                writes = variant["write_roles"]
                require_unique(roles, f"{label}: variant roles")
                require_unique(writes, f"{label}: variant write roles")
                require(
                    set(roles).issubset(expected_event_roles),
                    f"{label}: variant contains unknown role",
                )
                require(
                    "AUTHORITY_TRANSACTION_DOMAIN_STATE" in roles,
                    f"{label}: variant omits domain state",
                )
                require(
                    set(writes).issubset(roles),
                    f"{label}: write role is not a participant",
                )
                require(
                    primary_role in roles,
                    f"{label}: variant omits primary selector role",
                )
            _validate_case_variant_write_role_closure(
                label=label,
                contract=contract,
            )
            if selector_id in {
                "BODY_SESSION_CONTROL",
                "ACTUATION_AUTHORITY_DOMAIN",
            } and event["event_id"] not in (arbiter_facility_lifecycle_events):
                required_plant_roles = (
                    {
                        "AUTHORITY_TRANSACTION_DOMAIN_STATE",
                        "LOGICAL_SESSION_LINEAGE",
                        "BODY_SESSION_CONTROL",
                        "ACTUATION_DOMAIN_REGISTRY_AND_ARBITER",
                        "LOCAL_SECURITY_ENFORCEMENT",
                    }
                    if event["event_id"]
                    == "BODY_SESSION_CONTROL_GENESIS_FROM_SESSION_CREATION"
                    else plant_roles
                )
                require(
                    all(
                        required_plant_roles.issubset(set(variant["participant_roles"]))
                        for variant in contract["participant_role_variants"]
                    ),
                    (
                        f"{label}: plant transaction lacks "
                        "parent/body/domain/security closure"
                    ),
                )
            if event["event_id"] in {
                "FINALIZE_SOURCE_LOGICAL_SESSION_PERMANENT_RETIREMENT",
                "RECLAIM_SOURCE_OBSERVER_TARGET_HISTORY_DURING_PERMANENT_RETIREMENT",
                "SEAL_UNRESOLVED_OBSERVER_TARGETS",
            }:
                require(
                    all(
                        source_retirement_roles.issubset(
                            set(variant["participant_roles"])
                        )
                        for variant in contract["participant_role_variants"]
                    ),
                    f"{label}: source retirement omits a selector boundary",
                )
            require(
                "REMOTE_SELECTOR_RESPONSE_AS_CURRENTNESS"
                in contract["forbidden_substitutes"],
                f"{label}: remote selector response can grant currentness",
            )
            require_exact(
                contract["static_role_policy_and_bounds"],
                role_policy_and_bounds,
                f"{label}: static role policy and bounds",
            )
            require_exact(
                set(contract["participant_set_entry_kinds"]),
                {
                    "CURRENT_SELECTOR_PARTICIPANT",
                    "LOST_REGISTERED_PARTICIPANT_EVIDENCE_ONLY",
                },
                f"{label}: dynamic participant entry kinds",
            )
            require_exact(
                contract["pre_cas_semantic_commitment"],
                semantic_commitment,
                f"{label}: pre-CAS semantic commitment type",
            )
            require_exact(
                contract["prior_installed_evidence_receipt"],
                prior_installed_evidence,
                f"{label}: prior-installed evidence type",
            )
            require_exact(
                contract["post_candidate_installed_state_sidecar"],
                post_candidate_sidecar_type,
                f"{label}: post-candidate sidecar type",
            )
            atomic_conditions = [
                item
                for item in event["atomic_pre_cas_payloads"]
                if item["artifact"] == cas_condition
            ]
            require_exact(
                len(atomic_conditions),
                1,
                f"{label}: authority CAS condition count",
            )
            semantic_commitments = [
                item
                for item in event["atomic_pre_cas_payloads"]
                if item["artifact"] == semantic_commitment
            ]
            require_exact(
                len(semantic_commitments),
                1,
                f"{label}: pre-CAS semantic commitment count",
            )
            require_exact(
                semantic_commitments[0]["constructed"],
                "AFTER_EVENT_FACT_BEFORE_CAS_AND_CANDIDATES",
                f"{label}: pre-CAS semantic commitment construction order",
            )
            security_projections = [
                item
                for item in event["atomic_pre_cas_payloads"]
                if item["artifact"] == local_security_projection
            ]
            compares_local_security = bool(participant_variants) and all(
                "LOCAL_SECURITY_ENFORCEMENT" in variant["participant_roles"]
                for variant in participant_variants
            )
            require_exact(
                len(security_projections),
                (
                    1
                    if selector_id != "SECURITY_AUTHORITY" and compares_local_security
                    else 0
                ),
                f"{label}: local security projection count",
            )
            if security_projections:
                require_exact(
                    security_projections[0]["exposure"],
                    "NEVER_AS_AN_INDEPENDENT_CURRENTNESS_ROOT",
                    f"{label}: local security projection authority",
                )
            require(
                (
                    "DIRECT_EXACT_AUTHORITY_REALM_KEY_FIELD_ON_EVERY_REALM_"
                    "SCOPED_INPUT_OUTPUT_FACT_COMMITMENT_CANDIDATE_RECEIPT_"
                    "AND_SIDECAR"
                )
                in event["pre_cas_content"]["required_bindings"],
                f"{label}: realm-scoped objects lack direct realm key",
            )
            consumed = {item["artifact"] for item in event["consumes"]}
            require_exact(
                local_security_projection in consumed,
                bool(security_projections),
                f"{label}: local security projection consume/CAS parity",
            )
            require(
                {
                    qualification_receipt,
                    participant_set,
                    role_policy_and_bounds,
                }.issubset(consumed),
                (
                    f"{label}: qualification, dynamic participant set, or "
                    "static role policy is missing"
                ),
            )
            sidecars = event["post_cas_sidecars"]
            by_artifact = {item["artifact"]: item for item in sidecars}
            require(
                {
                    installed_root,
                    transaction_receipt,
                    selectors[selector_id]["generic_receipt"],
                    persistence_manifest,
                }.issubset(by_artifact),
                f"{label}: authority receipt DAG is incomplete",
            )
            receipt_free_commitments = {
                item["artifact"]
                for item in sidecars
                if item.get("dependency_class")
                == ("RECEIPT_FREE_POST_CANDIDATE_INSTALLED_STATE_COMMITMENT")
            }
            for item in sidecars:
                if item.get("dependency_class") == (
                    "RECEIPT_FREE_POST_CANDIDATE_INSTALLED_STATE_COMMITMENT"
                ):
                    require_exact(
                        item["sidecar_type"],
                        post_candidate_sidecar_type,
                        f"{label}: post-candidate sidecar type",
                    )
            require_exact(
                set(by_artifact[installed_root]["depends_on"]),
                receipt_free_commitments,
                f"{label}: installed-state root dependencies",
            )
            require_exact(
                by_artifact[transaction_receipt]["depends_on"],
                [installed_root],
                f"{label}: transaction receipt dependencies",
            )
            require(
                transaction_receipt
                in by_artifact[selectors[selector_id]["generic_receipt"]]["depends_on"],
                f"{label}: selector receipt does not depend on transaction receipt",
            )
            manifest_sidecar = by_artifact[persistence_manifest]
            manifest_dependencies_by_case = manifest_sidecar.get(
                "depends_on_by_semantic_case",
                {},
            )
            manifest_dependency_union = set(manifest_sidecar["depends_on"])
            for case_dependencies in manifest_dependencies_by_case.values():
                manifest_dependency_union.update(case_dependencies)
            post_persistence_artifacts = {
                artifact
                for artifact, sidecar_value in by_artifact.items()
                if persistence_manifest in sidecar_value["depends_on"]
            }
            pre_persistence_artifacts = (
                set(by_artifact) - {persistence_manifest} - post_persistence_artifacts
            )
            require_exact(
                manifest_dependency_union,
                pre_persistence_artifacts,
                f"{label}: persistence manifest dependency closure",
            )
            if manifest_dependencies_by_case:
                for semantic_case in event["transition_cases"]:
                    semantic_case_id = semantic_case["semantic_case_id"]
                    applicable_artifacts = {
                        item["artifact"]
                        for item in sidecars
                        if item["artifact"] in pre_persistence_artifacts
                        and (
                            "applies_to_semantic_case_ids" not in item
                            or semantic_case_id in item["applies_to_semantic_case_ids"]
                        )
                    }
                    effective_dependencies = set(manifest_sidecar["depends_on"]) | set(
                        manifest_dependencies_by_case.get(semantic_case_id, [])
                    )
                    require_exact(
                        effective_dependencies,
                        applicable_artifacts,
                        (
                            f"{label}.{semantic_case_id}: persistence manifest "
                            "case-specific dependency closure"
                        ),
                    )
            persistence_index = next(
                index
                for index, item in enumerate(sidecars)
                if item["artifact"] == persistence_manifest
            )
            require(
                all(
                    index < persistence_index
                    for index, item in enumerate(sidecars)
                    if item["artifact"] in pre_persistence_artifacts
                )
                and all(
                    index > persistence_index
                    for index, item in enumerate(sidecars)
                    if item["artifact"] in post_persistence_artifacts
                ),
                f"{label}: persistence boundary ordering is invalid",
            )
            for artifact, sidecar_value in by_artifact.items():
                require(
                    "EXACT_AUTHORITY_REALM_KEY"
                    in sidecar_value.get("additional_bindings", []),
                    f"{label}: sidecar {artifact} lacks direct realm key",
                )
            for forbidden in (
                "AUTHORITY_TRANSACTION_COMMIT_RECEIPT",
                "AUTHORITY_TRANSACTION_INSTALLED_STATE_ROOT",
                "AUTHORITY_TRANSACTION_PERSISTENCE_MANIFEST",
            ):
                require(
                    forbidden in event["pre_cas_content"]["forbidden_bindings"],
                    f"{label}: pre-CAS content permits {forbidden}",
                )
            require(
                "POST_CANDIDATE_INSTALLED_STATE_SIDECAR_COMMITMENT"
                in event["pre_cas_content"]["forbidden_bindings"],
                f"{label}: CAS input can bind a post-candidate commitment",
            )

    for selector_id in set(selectors) - set(authority_selector_roles):
        for event in selectors[selector_id]["events"]:
            require(
                "authority_transaction_contract" not in event,
                f"{selector_id}.{event['event_id']}: non-domain selector "
                "claims realm authority transaction placement",
            )


def _validate_critical_architecture(data: dict[str, Any]) -> None:
    selectors, events, domains = _selector_indexes(data)

    def event_edges(
        key: tuple[str, str],
        state_domain: str,
    ) -> set[tuple[str, str]]:
        require(key in events, f"missing critical event {key}")
        edge_catalog = {
            edge["edge_id"]: edge for edge in selectors[key[0]]["state_edge_catalog"]
        }
        return {
            (edge["from_state"], edge["to_state"])
            for case in events[key]["transition_cases"]
            for edge in (
                case.get("state_edges")
                or [edge_catalog[ref] for ref in case["state_edge_refs"]]
            )
            if edge["state_domain"] == state_domain
        }

    def artifact_names(event: dict[str, Any], field: str) -> set[str]:
        return {item["artifact"].split("::", 1)[-1] for item in event[field]}

    actuation_profile = data["actuation_authority_domain_registry_profile"]
    require_exact(
        actuation_profile["stable_selector_key"]["fields"],
        ["PHYSICAL_ACTUATION_JURISDICTION_KEY"],
        "actuation stable selector key",
    )
    require_exact(
        actuation_profile["stable_selector_key"][
            "registry_incarnation_is_key_coordinate"
        ],
        False,
        "actuation registry-incarnation key exclusion",
    )
    require_exact(
        domains[("ACTUATION_AUTHORITY_DOMAIN", "ROOT")]["key_coordinates"],
        ["PHYSICAL_ACTUATION_JURISDICTION_KEY"],
        "actuation root coordinates",
    )
    require(
        "joint_selector_transaction_profile_ref"
        not in events[
            (
                "ACTUATION_AUTHORITY_DOMAIN",
                "CONFIRM_ACTUATION_AUTHORITY_DOMAIN_GENERATION_GENESIS",
            )
        ],
        "domain confirmation must be a registry-only CAS",
    )
    _require_binding(
        events,
        (
            "BODY_SESSION_CONTROL",
            "BODY_SESSION_CONTROL_GENESIS_FROM_SESSION_CREATION",
        ),
        "CONDITIONALLY_COMPARE_CURRENT_DOMAIN_REGISTRY_ENTRY_IS_RESERVED_FOR_THIS_GENERATION",
    )
    _require_binding(
        events,
        (
            "BODY_SESSION_CONTROL",
            "RECONCILE_BODY_ACTUATION_DOMAIN_GENERATION_GENESIS",
        ),
        "EXACT_ACTUATION_AUTHORITY_DOMAIN_GENERATION_CONFIRMATION_RECEIPT",
    )
    owner_states = set(
        domains[("ACTUATION_AUTHORITY_DOMAIN", "ACTUATION_AUTHORITY_DOMAIN_ENTRY")][
            "states"
        ]
    )
    require(
        {
            "RESERVED_PARTIAL_RETIREMENT_FENCED",
            "RESERVED_PARTIAL_RETIREMENT_RETIRED",
        }.issubset(owner_states),
        "reserved-partial actuation-domain states are incomplete",
    )
    require_exact(
        event_edges(
            (
                "ACTUATION_AUTHORITY_DOMAIN",
                "FENCE_RESERVED_ACTUATION_AUTHORITY_DOMAIN_FOR_PARTIAL_BODY_RETIREMENT",
            ),
            "ACTUATION_AUTHORITY_DOMAIN_ENTRY",
        ),
        {
            (
                "RESERVED_FOR_GENERATION_GENESIS_FENCED",
                "RESERVED_PARTIAL_RETIREMENT_FENCED",
            )
        },
        "reserved-partial domain fence edge",
    )
    for partial_retirement_event in (
        "RETIRE_BODY_ACTUATION_BOUNDARY_AFTER_PHYSICAL_QUIESCENCE",
        "ISOLATE_RESERVED_ACTUATION_AUTHORITY_DOMAIN_AFTER_PARTIAL_BODY_STATE_LOSS",
    ):
        require(
            (
                "RESERVED_PARTIAL_RETIREMENT_FENCED",
                "RESERVED_PARTIAL_RETIREMENT_RETIRED",
            )
            in event_edges(
                ("ACTUATION_AUTHORITY_DOMAIN", partial_retirement_event),
                "ACTUATION_AUTHORITY_DOMAIN_ENTRY",
            ),
            f"{partial_retirement_event}: missing reserved-partial retirement",
        )
    release_edges = event_edges(
        (
            "ACTUATION_AUTHORITY_DOMAIN",
            "RELEASE_RESERVED_ACTUATION_AUTHORITY_DOMAIN_AFTER_PARTIAL_BODY_RETIREMENT",
        ),
        "ACTUATION_AUTHORITY_DOMAIN_ENTRY",
    )
    require_exact(
        release_edges,
        {
            (
                "RESERVED_PARTIAL_RETIREMENT_RETIRED",
                "UNOWNED_PHYSICALLY_ISOLATED",
            )
        },
        "reserved-partial release edge",
    )
    require(
        (
            "RESERVED_FOR_GENERATION_GENESIS_FENCED",
            "UNOWNED_PHYSICALLY_ISOLATED",
        )
        not in release_edges,
        "reserved-partial release bypasses terminal domain retirement",
    )

    lineage = data["logical_session_generation_lineage_profile"]
    require_exact(
        lineage["creation_scopes"],
        ["SIMULATION_SERVICE", "PLANT_CONTROL"],
        "ADR-001 creation scopes",
    )
    require_exact(
        lineage["required_child_role_sets"],
        {
            "PLANT_CONTROL": [
                "BODY_SESSION_CONTROL_STATE",
                "OBSERVER_AUTHORIZATION_STATE",
            ],
            "SIMULATION_SERVICE": [
                "SIMULATION_SESSION_STATE",
                "OBSERVER_AUTHORIZATION_STATE",
            ],
        },
        "ADR-001 child-role sets",
    )
    require(
        "GENERATION_PARTIAL_RETIREMENT_PREPARED"
        in domains[("LOGICAL_SESSION_GENERATION_LINEAGE", "ROOT")]["states"],
        "ADR-001 lacks the partial-retirement preparation state",
    )
    require_exact(
        event_edges(
            (
                "LOGICAL_SESSION_GENERATION_LINEAGE",
                "PREPARE_PARTIAL_LOGICAL_SESSION_GENERATION_RETIREMENT",
            ),
            "ROOT",
        ),
        {
            (
                "GENERATION_ALLOCATED_PENDING_CHILD_GENESIS",
                "GENERATION_PARTIAL_RETIREMENT_PREPARED",
            )
        },
        "ADR-001 partial-retirement prepare edge",
    )
    require_exact(
        event_edges(
            (
                "LOGICAL_SESSION_GENERATION_LINEAGE",
                "BEGIN_PARTIAL_LOGICAL_SESSION_GENERATION_RETIREMENT",
            ),
            "ROOT",
        ),
        {
            (
                "GENERATION_PARTIAL_RETIREMENT_PREPARED",
                "GENERATION_RETIRING",
            )
        },
        "ADR-001 partial-retirement begin edge",
    )
    require_exact(
        lineage["observer_rule"]["attach_allocates_new_adr001_lineage"],
        False,
        "observer attach ADR-001 allocation",
    )
    require_exact(
        lineage["observer_rule"]["observer_logical_session_id"],
        "DOES_NOT_EXIST",
        "observer logical-session namespace",
    )
    require_exact(
        set(lineage["finalization"]["does_not_require"]),
        {
            "REMOTE_DISTRIBUTED_AUTHORIZATION_CLOSURE",
            "RETAINED_TRANSPORT_QUIESCENCE",
            "OBSERVER_TARGET_CHECKPOINT_PUBLICATION",
        },
        "parent finalization non-requirements",
    )
    require(
        {
            "EXACT_SERVER_AUTHORITY_CUT",
            "COMPLETE_DURABLE_PENDING_TARGET_ROOT",
        }.issubset(lineage["finalization"]["requires"]),
        "parent finalization lacks local observer cut or pending root",
    )

    require_exact(
        set(domains[("OBSERVER_AUTHORIZATION", "ROOT")]["states"]),
        {
            "UNINITIALIZED",
            "PENDING_PARENT_CONFIRMATION",
            "ACTIVE",
            "RETIRED_DRAIN_ONLY",
            "TERMINAL",
        },
        "observer authorization root states",
    )
    target_domain = domains[
        ("OBSERVER_ATTACHMENT_TARGET_HISTORY", "TARGET_HISTORY_ENTRY")
    ]
    require_exact(
        target_domain["key_coordinates"],
        [
            "SERVER_AUTHORITY_REALM",
            "SOURCE_SESSION_KIND",
            "SOURCE_LOGICAL_SESSION_ID",
            "AUTHENTICATED_REQUESTER_PRINCIPAL",
        ],
        "observer target-history key coordinates",
    )
    require_exact(
        set(target_domain["states"]),
        {
            "ABSENT",
            "CURRENT_SOURCE_GENERATION",
            "SOURCE_AUTHORIZATION_RETIRED_PENDING_PARENT_FINALIZATION",
            "SOURCE_GENERATION_FINALIZED_PENDING_CHECKPOINT_PUBLICATION",
            "CHECKPOINT_PUBLISHED",
            "SOURCE_PERMANENTLY_RETIRED_PUBLISHED_TOMBSTONE",
            "SOURCE_PERMANENTLY_RETIRED_SEALED_UNRESOLVED_TOMBSTONE",
        },
        "observer target-history phases",
    )
    require_exact(
        events[
            (
                "OBSERVER_ATTACHMENT_TARGET_HISTORY",
                "RETIRE_OBSERVER_SESSION_GENERATION",
            )
        ]["operation_scope"],
        "BOUNDED_KEY_SET",
        "observer target retirement scope",
    )
    require(
        (
            "OBSERVER_ATTACHMENT_TARGET_HISTORY",
            "FINALIZE_LOGICAL_SESSION_GENERATION_IN_LINEAGE",
        )
        not in events,
        "parent finalization must not directly mutate target history",
    )
    reconciliation = events[
        (
            "OBSERVER_ATTACHMENT_TARGET_HISTORY",
            "RECONCILE_OBSERVER_TARGET_HISTORY_AFTER_PARENT_FINALIZATION",
        )
    ]
    require_exact(
        reconciliation["operation_scope"],
        "BOUNDED_KEY_SET",
        "observer target post-parent reconciliation scope",
    )
    require(
        "joint_selector_transaction_profile_ref" not in reconciliation,
        "post-parent target reconciliation must be a separate CAS",
    )
    require_exact(
        reconciliation["pre_cas_content"]["artifact"].split("::", 1)[-1],
        "ObserverTargetHistoryParentFinalizationFact",
        "observer target reconciliation fact",
    )
    require(
        "ObserverTargetHistoryParentFinalizationReceipt"
        in artifact_names(reconciliation, "post_cas_sidecars"),
        "observer target reconciliation receipt is missing",
    )
    publication = events[
        (
            "OBSERVER_ATTACHMENT_TARGET_HISTORY",
            "PUBLISH_OBSERVER_ATTACHMENT_TARGET_LINEAGE_CHECKPOINT",
        )
    ]
    require_exact(
        publication["operation_scope"],
        "EXACT_ONE_KEY",
        "observer target checkpoint publication scope",
    )
    for binding in (
        "REMOTE_EVIDENCE_IS_EXACTLY_NO_ACCEPTED_GRANT_NO_REMOTE_AUTHORITY_OR_TERMINAL_GRANT_HISTORY_COMPLETE_CLOSURE",
        "NO_ACCEPTED_GRANT_BRANCH_FORBIDS_DISTRIBUTED_OR_TRANSPORT_SUCCESS_RECEIPTS",
        "TERMINAL_GRANT_BRANCH_REQUIRES_COMPLETE_DISTRIBUTED_AUTHORIZATION_CLOSURE_AND_TRANSPORT_QUIESCENCE_FOR_EVERY_GRANT_AND_BOUNDARY",
        "EXACT_ONE_ELIGIBLE_PENDING_TARGET_ENTRY_MOVES_TO_CHECKPOINT_PUBLISHED",
    ):
        require(
            binding in publication["pre_cas_content"]["required_bindings"],
            f"target checkpoint publication lacks {binding}",
        )
    publication_partition = publication["publication_remote_evidence_partition"]
    require_exact(
        {
            key
            for key in publication_partition
            if key
            in {
                "NO_ACCEPTED_GRANT_NO_REMOTE_AUTHORITY",
                "TERMINAL_GRANT_HISTORY_COMPLETE_CLOSURE",
            }
        },
        {
            "NO_ACCEPTED_GRANT_NO_REMOTE_AUTHORITY",
            "TERMINAL_GRANT_HISTORY_COMPLETE_CLOSURE",
        },
        "observer publication remote-evidence union",
    )
    require_exact(
        publication_partition["type"],
        "ObserverAttachmentTargetPublicationRemoteEvidence",
        "observer publication remote-evidence type",
    )

    terminal = events[("OBSERVER_AUTHORIZATION", "TERMINATE_GRANT")]
    terminal_sidecars = artifact_names(terminal, "post_cas_sidecars")
    require(
        {
            "ObserverGrantReattachmentPolicyAssessment",
            "ObserverGrantFreshAttachPolicyAssessment",
        }.issubset(terminal_sidecars),
        "grant terminalization lacks both immutable policy assessments",
    )
    require(
        {
            "ObserverGrantReattachmentPolicyResult",
            "ObserverGrantFreshAttachPolicyResult",
        }.isdisjoint(terminal_sidecars),
        "grant terminalization must not mint final policy results",
    )
    publication_sidecars = artifact_names(publication, "post_cas_sidecars")
    require(
        {
            "ObserverGrantReattachmentPolicyResult",
            "ObserverGrantFreshAttachPolicyResult",
        }.issubset(publication_sidecars),
        "target publication lacks final policy results",
    )
    reattach = events[("OBSERVER_AUTHORIZATION", "REATTACH_FROM_TERMINAL_GRANT")]
    origin_partition = reattach["reattachment_origin_evidence_partition"]
    require_exact(
        origin_partition["type"],
        "ObserverGrantReattachmentOriginEvidence",
        "reattachment origin type",
    )
    require(
        {
            "CURRENT_GENERATION_TERMINAL",
            "PUBLISHED_PREDECESSOR_TARGET",
        }.issubset(origin_partition),
        "reattachment origin branches are incomplete",
    )
    require(
        "ObserverGrantReattachmentPolicyResult"
        in origin_partition["CURRENT_GENERATION_TERMINAL"]["forbids"],
        "same-generation reattach does not forbid a final result",
    )
    require(
        "ObserverGrantReattachmentPolicyAssessment_AS_AUTHORITY"
        in origin_partition["PUBLISHED_PREDECESSOR_TARGET"]["forbids"],
        "published-predecessor reattach does not forbid assessment authority",
    )

    fence = events[
        (
            "ACTUATION_AUTHORITY_DOMAIN",
            "FENCE_BODY_ACTUATION_BOUNDARY_AND_SELECT_RESTRICTIVE_ACTION",
        )
    ]
    selection = fence["restrictive_selection_partition"]
    require_exact(
        selection["ordered_branches"],
        [
            "JOIN_IDENTICAL_ACTION",
            "START_PROFILE_DOMINATING_ACTION",
            "START_QUALIFIED_ESTOP_SEVERITY_OVERRIDE",
            "RECORD_EQUAL_OR_LOWER_CUT_WITHOUT_INVOCATION",
            "FENCE_INCOMPARABLE_ACTION_FOR_OPERATOR_RESOLUTION",
        ],
        "restrictive-selection precedence",
    )
    require_exact(
        set(selection["start_evidence"]),
        {
            "DOMINATES_COMPLETE_FRONTIER",
            "EMPTY_FRONTIER_PROFILE_AUTHORIZED",
            "QUALIFIED_ESTOP_SEVERITY_OVERRIDE",
        },
        "restrictive-action start-evidence union",
    )
    require_exact(
        set(selection["override_member_evidence"]),
        {
            "HOLD_CLEAR_SUPERSEDED_OR_SERIALIZED",
            "PRIOR_RESTRICTIVE_ACTION_PRESERVED_WITH_INDEPENDENT_ESTOP_ASSERTION",
        },
        "ESTOP override frontier-member evidence",
    )
    override_cases = [
        case
        for case in fence["transition_cases"]
        if case["semantic_case_id"].startswith(
            "START_QUALIFIED_ESTOP_SEVERITY_OVERRIDE__"
        )
    ]
    require_exact(len(override_cases), 1, "ESTOP override semantic-case count")
    override_definition = next(
        item
        for item in fence["decision_model"]["evidence_variant_definitions"]
        if item["evidence_variant_id"] == override_cases[0]["evidence_variant_id"]
    )
    require(
        "PRE_CAS_CONTENT.severity_override_proof"
        in (
            set(fence["decision_model"]["common_required_fields"])
            | set(override_definition["required_fields"])
        ),
        "ESTOP override case lacks its exact proof",
    )
    require(
        "BodyFailSafeSeverityOverrideProof" in artifact_names(fence, "consumes"),
        "ESTOP override does not consume its proof",
    )

    upgrade = events[("BODY_SESSION_CONTROL", "UPGRADE_BODY_FAIL_SAFE_TO_ESTOP")]
    require(
        any(
            "UPGRADE_HOLD_OUTCOME_UNKNOWN_TO_ESTOP" in case["semantic_case_id"]
            for case in upgrade["transition_cases"]
        ),
        "ESTOP upgrade omits HOLD_OUTCOME_UNKNOWN",
    )
    for qualification_key in (
        (
            "ACTUATION_AUTHORITY_DOMAIN",
            "ACTIVATE_BODY_ACTUATION_GATE_WITH_FRESH_EPOCH",
        ),
        ("BODY_SESSION_CONTROL", "ISSUE_BODY_COMMAND_FRESHNESS_GRANT"),
        ("BODY_SESSION_CONTROL", "UPGRADE_BODY_FAIL_SAFE_TO_ESTOP"),
    ):
        require(
            "BodyFailSafeEscalationQualificationRoot"
            in artifact_names(events[qualification_key], "consumes"),
            f"{qualification_key}: escalation qualification root is missing",
        )
    qualification = data["body_actuation_arbiter_profile"][
        "fail_safe_escalation_qualification"
    ]
    require(
        "HOLD_OUTCOME_UNKNOWN" in qualification["reachable_frontier_members_include"],
        "escalation qualification omits HOLD_OUTCOME_UNKNOWN",
    )
    require_exact(
        qualification["failure_rule"],
        (
            "MISSING_UNKNOWN_DEFAULT_STALE_PROFILE_PARTIAL_FRONTIER_OR_"
            "NO_TOKEN_EVIDENCE_DISABLES_BOTH_REMOTE_HOLD_AND_REMOTE_ESTOP"
        ),
        "remote HOLD/ESTOP fail-closed qualification rule",
    )

    for estop_reconciliation_key in (
        ("BODY_SESSION_CONTROL", "LATCH_BODY_ESTOP"),
        ("BODY_SESSION_CONTROL", "COMPLETE_RESERVED_FAIL_SAFE_COMMAND"),
    ):
        estop_event = events[estop_reconciliation_key]
        consumed = artifact_names(estop_event, "consumes")
        require(
            {
                "BodyActuationRestrictiveActionResultReceipt",
                "BodyActuationArbiterTransitionReceiptSetRoot",
            }.issubset(consumed),
            f"{estop_reconciliation_key}: incomplete ADR-007 result lineage",
        )
        contract = estop_event["estop_result_reconciliation_contract"]
        require_exact(
            contract["result"],
            "RESTRICTIVE_ACTION_ACCEPTED",
            f"{estop_reconciliation_key}: accepted result",
        )
    latch = events[("BODY_SESSION_CONTROL", "LATCH_BODY_ESTOP")]
    body_edge_catalog = {
        edge["edge_id"]: edge
        for edge in selectors["BODY_SESSION_CONTROL"]["state_edge_catalog"]
    }
    require(
        all(
            any(
                edge["state_domain"] == "ARBITER_RECEIPT_CONSUMPTION_INDEX"
                and edge["to_state"] == "CONSUMED"
                for edge in (
                    case.get("state_edges")
                    or [body_edge_catalog[ref] for ref in case["state_edge_refs"]]
                )
            )
            for case in latch["transition_cases"]
        ),
        "LATCH_BODY_ESTOP has a direct path without receipt-set consumption",
    )

    simulation_event_ids = {
        event["event_id"] for event in selectors["SIMULATION_SESSION_STATE"]["events"]
    }
    require_exact(
        simulation_event_ids,
        {
            "SIMULATION_SESSION_STATE_GENESIS_FROM_GENERATION_CREATION",
            "ACTIVATE_SIMULATION_SESSION_AFTER_PARENT_CONFIRMATION",
            "RETIRE_SIMULATION_SESSION_GENERATION",
            "FINALIZE_SIMULATION_SESSION_GENERATION",
        }
        | set(data["simulation_session_state_profile"]["subresource_event_kinds"]),
        "simulation lifecycle event surface",
    )

    serialized = canonical_bytes(data)
    require(
        b"ObserverAttachmentLineageId" not in serialized,
        "obsolete observer attachment lineage ID remains",
    )
    for obsolete_hardware_alias_fragment in (
        (b"physical-actuation-jurisdiction-hardware-install-authorization-type"),
        b"PhysicalActuationJurisdictionHardwareInstallAuthorization",
    ):
        require(
            obsolete_hardware_alias_fragment not in serialized,
            "obsolete hardware-install authorization alias remains",
        )
    require(
        b"ATTACH_OBSERVER" not in canonical_bytes(lineage["creation_scopes"]),
        "observer attach remains an ADR-001 creation scope",
    )


_SEMANTIC_VALIDATION_MODES = {
    (False, False, False): "ALLOCATION_DIAGNOSTIC_STRICT_ARCHITECTURE",
    (False, False, True): "LEGACY_BROAD_DIAGNOSTIC",
    (True, False, False): "STRICT_COMPLETE",
    (True, True, False): "EXACT_REVIEW_CANDIDATE",
}

_CLI_VALIDATION_MODES = {
    (False, False, False, False, False): "STRICT_COMPLETE_SEMANTICS",
    (True, False, False, False, False): "STRICT_COMPLETE_SEMANTICS_AND_PROBES",
    (False, True, False, False, False): "PROBES_ONLY",
    (False, False, True, False, False): "HOSTILE_SELF_TEST",
    (False, False, False, True, False): "INVENTORY_GAP_REPORT",
    (False, False, False, False, True): "EXACT_REVIEW_CANDIDATE_SEMANTICS_AND_PROBES",
}


def _semantic_validation_mode(
    *,
    require_complete_allocation: bool,
    allow_incomplete_allocation: bool,
    allow_known_incomplete: bool,
) -> str:
    """Map the three compatibility flags onto one closed validation mode."""

    require(
        type(require_complete_allocation) is bool
        and type(allow_incomplete_allocation) is bool
        and type(allow_known_incomplete) is bool,
        "semantic validation mode flags must be booleans",
    )
    flags = (
        require_complete_allocation,
        allow_incomplete_allocation,
        allow_known_incomplete,
    )
    require(
        flags in _SEMANTIC_VALIDATION_MODES,
        (
            "semantic validation flags do not select a closed mode; "
            "allocation-only review requires (true,true,false), strict "
            "validation requires (true,false,false), and diagnostic modes "
            "require (false,false,*)"
        ),
    )
    return _SEMANTIC_VALIDATION_MODES[flags]


def _run_semantic_validation_mode_self_test() -> int:
    """Exhaust all Boolean flag tuples and reject non-Boolean lookalikes."""

    accepted: dict[tuple[bool, bool, bool], str] = {}
    rejected = 0
    for require_complete in (False, True):
        for allow_incomplete in (False, True):
            for allow_known in (False, True):
                flags = (require_complete, allow_incomplete, allow_known)
                try:
                    mode = _semantic_validation_mode(
                        require_complete_allocation=require_complete,
                        allow_incomplete_allocation=allow_incomplete,
                        allow_known_incomplete=allow_known,
                    )
                except ClosureCheckError:
                    rejected += 1
                else:
                    accepted[flags] = mode
    require_exact(
        accepted,
        _SEMANTIC_VALIDATION_MODES,
        "semantic validation closed-mode truth table",
    )
    require_exact(rejected, 4, "semantic validation rejected Boolean tuples")
    for hostile in (0, 1, None, "true"):
        try:
            _semantic_validation_mode(
                require_complete_allocation=hostile,
                allow_incomplete_allocation=False,
                allow_known_incomplete=False,
            )
        except ClosureCheckError:
            rejected += 1
        else:
            fail("semantic validation accepted a non-Boolean mode flag")
    return len(accepted) + rejected


def _cli_validation_mode(
    *,
    run_probes: bool,
    probes_only: bool,
    self_test: bool,
    inventory_gap_report: bool,
    review_candidate: bool,
) -> str:
    """Select one closed CLI action without a validation-bypass combination."""

    flags = (
        run_probes,
        probes_only,
        self_test,
        inventory_gap_report,
        review_candidate,
    )
    require(
        all(type(flag) is bool for flag in flags),
        "selector closure CLI mode flags must be booleans",
    )
    require(
        flags in _CLI_VALIDATION_MODES,
        (
            "--run-probes, --probes-only, --self-test, "
            "--inventory-gap-report, and --review-candidate select "
            "mutually exclusive validation modes"
        ),
    )
    return _CLI_VALIDATION_MODES[flags]


def _run_cli_validation_mode_self_test() -> int:
    """Exhaust the CLI flag product and retain only the six declared modes."""

    accepted: dict[tuple[bool, bool, bool, bool, bool], str] = {}
    rejected = 0
    for flags in product((False, True), repeat=5):
        try:
            mode = _cli_validation_mode(
                run_probes=flags[0],
                probes_only=flags[1],
                self_test=flags[2],
                inventory_gap_report=flags[3],
                review_candidate=flags[4],
            )
        except ClosureCheckError:
            rejected += 1
        else:
            accepted[flags] = mode
    require_exact(
        accepted,
        _CLI_VALIDATION_MODES,
        "selector closure CLI closed-mode truth table",
    )
    require_exact(rejected, 26, "selector closure CLI rejected Boolean tuples")
    for hostile in (0, 1, None, "true"):
        try:
            _cli_validation_mode(
                run_probes=hostile,
                probes_only=False,
                self_test=False,
                inventory_gap_report=False,
                review_candidate=False,
            )
        except ClosureCheckError:
            rejected += 1
        else:
            fail("selector closure CLI accepted a non-Boolean mode flag")
    return len(accepted) + rejected


def _require_review_candidate_boundary(data: dict[str, Any]) -> None:
    """Admit only the exact fail-closed, unreviewed allocation boundary."""

    oracle = data.get("adr_allocation_oracle")
    require(
        isinstance(oracle, dict),
        "review-candidate source must contain the allocation oracle",
    )
    provenance_review = oracle.get("provenance_review")
    require(
        oracle.get("status") == "INCOMPLETE_FAIL_CLOSED"
        and isinstance(provenance_review, dict)
        and provenance_review.get("status") == "NOT_REVIEWED"
        and provenance_review.get("reviewed_assignment_sha256") == "0" * 64,
        (
            "review-candidate mode requires the exact "
            "INCOMPLETE_FAIL_CLOSED/NOT_REVIEWED/zero-reviewed-digest tuple"
        ),
    )


def _run_review_candidate_boundary_self_test() -> int:
    """Reject every optimistic or malformed review-candidate state mutation."""

    baseline = {
        "adr_allocation_oracle": {
            "status": "INCOMPLETE_FAIL_CLOSED",
            "provenance_review": {
                "status": "NOT_REVIEWED",
                "reviewed_assignment_sha256": "0" * 64,
            },
        }
    }
    _require_review_candidate_boundary(baseline)
    mutations = (
        lambda value: value.__setitem__("adr_allocation_oracle", None),
        lambda value: value["adr_allocation_oracle"].__setitem__("status", "COMPLETE"),
        lambda value: value["adr_allocation_oracle"].__setitem__("status", "UNKNOWN"),
        lambda value: value["adr_allocation_oracle"].__setitem__(
            "provenance_review", None
        ),
        lambda value: value["adr_allocation_oracle"]["provenance_review"].__setitem__(
            "status", "REVIEWED"
        ),
        lambda value: value["adr_allocation_oracle"]["provenance_review"].__setitem__(
            "reviewed_assignment_sha256", "1" * 64
        ),
    )
    rejected = 0
    for mutation in mutations:
        hostile = copy.deepcopy(baseline)
        mutation(hostile)
        try:
            _require_review_candidate_boundary(hostile)
        except ClosureCheckError:
            rejected += 1
        else:
            fail("review-candidate boundary accepted a hostile state mutation")
    require_exact(rejected, len(mutations), "review-candidate boundary mutants")
    return rejected


def validate_expanded_source(
    data: dict[str, Any],
    *,
    require_complete_allocation: bool = True,
    allow_incomplete_allocation: bool = False,
    allow_known_incomplete: bool = False,
    adr_snapshot_sink: Callable[[dict[Path, bytes]], None] | None = None,
) -> CheckSummary:
    _semantic_validation_mode(
        require_complete_allocation=require_complete_allocation,
        allow_incomplete_allocation=allow_incomplete_allocation,
        allow_known_incomplete=allow_known_incomplete,
    )
    require(isinstance(data, dict), "expanded source must be an object")
    _validate_closed_shapes(data)
    _validate_owned_resource_registry(data)
    require_exact(
        data["$schema"],
        "selector-closure.source.schema.v1.json",
        "expanded $schema",
    )
    adr_snapshots = _validate_adr_allocation_oracle(
        data,
        require_complete=(
            require_complete_allocation and not allow_incomplete_allocation
        ),
    )
    require_exact(
        data["schema"],
        "ncp.b01-selector-closure-source.v1",
        "expanded schema",
    )
    require_exact(data["normative"], False, "expanded normative flag")
    require_exact(data["candidate"], "1.0.0-rc.1", "expanded candidate")
    require_exact(data["task"], "B01", "expanded task")
    require_exact(
        data["generated_view"],
        "docs/adr/B01_SELECTOR_CLOSURE_MATRIX.md",
        "generated view",
    )
    require_exact(
        data["generated_by"],
        "scripts/generate_selector_closure_source.py",
        "generated-by command",
    )

    artifacts_list = data["artifacts"]
    require(isinstance(artifacts_list, list), "artifacts must be an array")
    require_exact(artifacts_list, sorted(artifacts_list), "artifact order")
    require_unique(artifacts_list, "artifact registry")
    require(
        all(
            isinstance(reference, str) and ALLOCATION_REF.fullmatch(reference)
            for reference in artifacts_list
        ),
        "artifact registry contains an invalid reference",
    )
    artifacts = set(artifacts_list)
    _validate_artifact_registry_usage(
        data,
        artifacts,
        allow_known_incomplete=allow_known_incomplete,
    )
    _validate_handoff_quiescence_bijections(data, artifacts)
    (
        domain_count,
        event_count,
        case_count,
        partition_branch_count,
        sidecar_count,
    ) = _validate_selector_structure(
        data,
        artifacts,
        allow_known_incomplete=allow_known_incomplete,
    )
    _validate_observer_grant_request_product_liveness(
        data,
        allow_known_incomplete=allow_known_incomplete,
    )
    _validate_observer_grant_closure_aggregation_contract(data)
    _validate_profile_references(data)
    _validate_global_key_registry(data)
    _validate_closure_commitments(data)
    _validate_observer_read_capture_bridge_profile(data)
    selectors, events, _ = _selector_indexes(data)
    _validate_joint_transactions(data, selectors, events)
    _, _, domains = _selector_indexes(data)
    _validate_source_issuance_index(data, selectors, events, domains)
    _validate_simulation_subresource_architecture(
        data,
        selectors,
        events,
        domains,
        artifacts,
    )
    _validate_independent_anchor_architecture(
        data,
        selectors,
        events,
        domains,
    )
    _validate_authority_transaction_architecture(data)
    _validate_critical_architecture(data)
    _verify_adr_snapshots_unchanged(adr_snapshots)
    if adr_snapshot_sink is not None:
        require(callable(adr_snapshot_sink), "ADR snapshot sink is not callable")
        adr_snapshot_sink(dict(adr_snapshots))

    return CheckSummary(
        selectors=len(data["selectors"]),
        state_domains=domain_count,
        events=event_count,
        semantic_cases=case_count,
        partition_branches=partition_branch_count,
        sidecars=sidecar_count,
        artifacts=len(artifacts),
        joint_transactions=len(data["joint_selector_transaction_profiles"]),
        expanded_sha256=canonical_sha256(data),
    )


def _verify_probe_script_binding(
    probe_id: str,
    binding: dict[str, Any],
    script_bytes: bytes,
) -> None:
    require_exact(
        len(script_bytes),
        binding["script_byte_length"],
        f"{probe_id}: script byte length",
    )
    require_exact(
        sha256(script_bytes).hexdigest(),
        binding["script_sha256"],
        f"{probe_id}: script digest",
    )


def _verify_probe_result(
    probe_id: str,
    binding: dict[str, Any],
    *,
    returncode: int,
    stdout: bytes,
    stderr: bytes,
) -> None:
    """Require one successful probe to match both authenticated output channels."""

    if returncode != 0:
        diagnostic = stderr.decode("utf-8", errors="replace")
        fail(f"{probe_id}: command failed with {returncode}: {diagnostic.strip()}")
    require_exact(stderr, b"", f"{probe_id}: stderr")
    require_exact(
        len(stdout),
        binding["stdout_byte_length"],
        f"{probe_id}: stdout byte length",
    )
    require_exact(
        sha256(stdout).hexdigest(),
        binding["stdout_sha256"],
        f"{probe_id}: stdout digest",
    )


def _run_probe_dependency_bound_self_test(data: dict[str, Any]) -> int:
    """Prove exact-bound admission and one-byte-over rejection for dependencies."""

    rejected = 0
    bindings = data["adversarial_probe_bindings"]["shared_source_bindings"]
    for source_id, binding in sorted(bindings.items()):
        declared_byte_length = binding["byte_length"]
        require(
            type(declared_byte_length) is int
            and 1 < declared_byte_length <= MAX_PROBE_DEPENDENCY_BYTES,
            f"{source_id}: dependency bound self-test length is invalid",
        )
        source_path = ROOT / binding["path"]
        exact_bound_source = read_bounded_regular_file(
            source_path,
            maximum_bytes=declared_byte_length,
            label=f"{source_id} dependency exact-bound self-test",
        )
        require_exact(
            len(exact_bound_source),
            declared_byte_length,
            f"{source_id}: dependency exact-bound byte length",
        )
        try:
            read_bounded_regular_file(
                source_path,
                maximum_bytes=declared_byte_length - 1,
                label=f"{source_id} dependency one-byte-over self-test",
            )
        except SelectorClosureCodecError:
            rejected += 1
        else:
            fail(f"{source_id}: accepted a one-byte-over dependency")
    return rejected


def _require_topological_probe_dependencies(
    probe_id: str,
    dependency_ids: list[str],
) -> None:
    """Require one exact flattened dependency closure in preload order."""

    require(
        len(dependency_ids) == len(set(dependency_ids)),
        f"{probe_id}: dependency closure contains a duplicate",
    )
    installed: set[str] = set()
    for source_id in dependency_ids:
        require(
            source_id in EXPECTED_SHARED_PROBE_SOURCES,
            f"{probe_id}: dependency closure names an unknown source",
        )
        direct = EXPECTED_SHARED_PROBE_SOURCES[source_id]["dependency_ids"]
        require(
            set(direct).issubset(installed),
            f"{probe_id}: dependency closure is not topologically ordered",
        )
        installed.add(source_id)


def run_bound_probes(data: dict[str, Any]) -> int:
    bindings = data["adversarial_probe_bindings"]
    require(isinstance(bindings, dict), "probe bindings must be an object")
    claim_boundary = bindings.get("claim_boundary")
    require_exact(
        claim_boundary,
        EXPECTED_PROBE_CLAIM_BOUNDARY,
        "probe claim boundary",
    )
    require_exact(
        set(bindings)
        - {"claim_boundary", "execution_profile", "shared_source_bindings"},
        set(EXPECTED_PROBE_REVIEW_COMMANDS),
        "bound probe set",
    )
    require_exact(
        bindings.get("execution_profile"),
        EXPECTED_PROBE_EXECUTION_PROFILE,
        "bound probe execution profile",
    )
    require_exact(
        set(EXPECTED_PROBE_CPU_SECONDS),
        set(EXPECTED_PROBE_REVIEW_COMMANDS),
        "bound probe CPU-limit set",
    )
    require_exact(
        set(EXPECTED_PROBE_WALL_SECONDS),
        set(EXPECTED_PROBE_REVIEW_COMMANDS),
        "bound probe wall-limit set",
    )
    for probe_id, cpu_seconds in EXPECTED_PROBE_CPU_SECONDS.items():
        require_exact(
            EXPECTED_PROBE_WALL_SECONDS[probe_id],
            cpu_seconds * 2,
            f"{probe_id}: scheduler-slack wall limit",
        )
    shared_bindings = bindings.get("shared_source_bindings")
    require(
        isinstance(shared_bindings, dict),
        "shared probe source bindings must be an object",
    )
    require_exact(
        set(shared_bindings),
        set(EXPECTED_SHARED_PROBE_SOURCES),
        "shared probe source set",
    )
    require_exact(
        {
            source_id
            for dependency_ids in EXPECTED_PROBE_DEPENDENCIES.values()
            for source_id in dependency_ids
        },
        set(EXPECTED_SHARED_PROBE_SOURCES),
        "used shared probe source set",
    )
    source_snapshots: dict[Path, tuple[bytes, int, str]] = {}

    def retain_source_snapshot(
        path: Path,
        raw: bytes,
        *,
        maximum_bytes: int,
        label: str,
    ) -> None:
        existing = source_snapshots.get(path)
        if existing is not None:
            require_exact(raw, existing[0], f"{label} repeated source snapshot")
            maximum_bytes = min(maximum_bytes, existing[1])
            label = existing[2]
        source_snapshots[path] = (raw, maximum_bytes, label)

    shared_sources: dict[str, tuple[str, str, bytes]] = {}
    for source_id, expected in sorted(EXPECTED_SHARED_PROBE_SOURCES.items()):
        binding = shared_bindings[source_id]
        require(
            isinstance(binding, dict),
            f"{source_id}: shared source binding must be an object",
        )
        require_exact(
            set(binding),
            {"byte_length", "dependency_ids", "module", "path", "sha256"},
            f"{source_id}: shared source binding keys",
        )
        require_exact(
            binding["dependency_ids"],
            expected["dependency_ids"],
            f"{source_id}: direct dependency IDs",
        )
        _require_topological_probe_dependencies(
            source_id,
            [*binding["dependency_ids"], source_id],
        )
        require_exact(binding["module"], expected["module"], f"{source_id}: module")
        require_exact(binding["path"], expected["path"], f"{source_id}: path")
        require(
            isinstance(binding["byte_length"], int)
            and not isinstance(binding["byte_length"], bool)
            and 0 < binding["byte_length"] <= MAX_PROBE_DEPENDENCY_BYTES,
            f"{source_id}: invalid bounded byte length",
        )
        require(
            isinstance(binding["sha256"], str)
            and SHA256_HEX.fullmatch(binding["sha256"]) is not None,
            f"{source_id}: invalid SHA-256",
        )
        source_path = Path(binding["path"])
        require(
            not source_path.is_absolute()
            and ".." not in source_path.parts
            and (ROOT / source_path)
            .resolve(strict=True)
            .is_relative_to(ROOT.resolve(strict=True)),
            f"{source_id}: shared source path escapes the repository",
        )
        source_bytes = read_bounded_regular_file(
            ROOT / source_path,
            maximum_bytes=MAX_PROBE_DEPENDENCY_BYTES,
            label=f"{source_id} shared probe source",
        )
        require_exact(
            len(source_bytes),
            binding["byte_length"],
            f"{source_id}: shared source byte length",
        )
        require_exact(
            sha256(source_bytes).hexdigest(),
            binding["sha256"],
            f"{source_id}: shared source digest",
        )
        retain_source_snapshot(
            ROOT / source_path,
            source_bytes,
            maximum_bytes=MAX_PROBE_DEPENDENCY_BYTES,
            label=f"{source_id} shared probe source",
        )
        shared_sources[source_id] = (
            binding["module"],
            binding["path"],
            source_bytes,
        )
    prepared_probes: list[
        tuple[str, dict[str, Any], str, bytes, tuple[tuple[str, str, bytes], ...]]
    ] = []
    for probe_id, binding in sorted(bindings.items()):
        if probe_id in {
            "claim_boundary",
            "execution_profile",
            "shared_source_bindings",
        }:
            continue
        require(isinstance(binding, dict), f"{probe_id}: invalid binding")
        require_exact(
            set(binding),
            EXPECTED_PROBE_BINDING_KEYS[probe_id],
            f"{probe_id}: binding keys",
        )
        require_exact(
            binding.get("review_command"),
            EXPECTED_PROBE_REVIEW_COMMANDS[probe_id],
            f"{probe_id}: review command",
        )
        require_exact(
            binding.get("source_path"),
            EXPECTED_PROBE_SOURCE_PATHS[probe_id],
            f"{probe_id}: source path",
        )
        require_exact(
            binding.get("dependency_ids"),
            EXPECTED_PROBE_DEPENDENCIES[probe_id],
            f"{probe_id}: dependency IDs",
        )
        _require_topological_probe_dependencies(
            probe_id,
            binding["dependency_ids"],
        )
        for digest_key in {"script_sha256", "stdout_sha256"}:
            require(
                isinstance(binding[digest_key], str)
                and SHA256_HEX.fullmatch(binding[digest_key]) is not None,
                f"{probe_id}.{digest_key}: invalid SHA-256",
            )
        for length_key, maximum in (
            ("script_byte_length", MAX_PROBE_SCRIPT_BYTES),
            ("stdout_byte_length", MAX_PROBE_OUTPUT_BYTES),
        ):
            require(
                type(binding[length_key]) is int and 0 < binding[length_key] <= maximum,
                f"{probe_id}.{length_key}: invalid exact byte length",
            )
        command = shlex.split(binding["review_command"])
        require(command, f"{probe_id}: empty command")
        require_exact(command[0], "python3", f"{probe_id}: interpreter")
        require_exact(len(command), 2, f"{probe_id}: command shape")
        require_exact(
            command[1],
            binding["source_path"],
            f"{probe_id}: review command source path",
        )
        script = Path(binding["source_path"])
        require(
            not script.is_absolute() and ".." not in script.parts,
            f"{probe_id}: command escapes repository",
        )
        require(
            (ROOT / script)
            .resolve(strict=True)
            .is_relative_to(ROOT.resolve(strict=True)),
            f"{probe_id}: probe script resolves outside the repository",
        )
        script_bytes = read_bounded_regular_file(
            ROOT / script,
            maximum_bytes=MAX_PROBE_SCRIPT_BYTES,
            label=f"{probe_id} probe script",
        )
        _verify_probe_script_binding(probe_id, binding, script_bytes)
        retain_source_snapshot(
            ROOT / script,
            script_bytes,
            maximum_bytes=MAX_PROBE_SCRIPT_BYTES,
            label=f"{probe_id} probe script",
        )
        dependencies = tuple(
            shared_sources[source_id] for source_id in binding["dependency_ids"]
        )
        prepared_probes.append(
            (probe_id, binding, binding["source_path"], script_bytes, dependencies)
        )

    ran = 0
    for probe_id, binding, script_path, script_bytes, dependencies in prepared_probes:
        require(
            bool(sys.executable),
            f"{probe_id}: checker has no exact Python interpreter path",
        )
        returncode, stdout, stderr_bytes = _run_bounded_probe(
            script_bytes,
            probe_id=probe_id,
            script_path=script_path,
            dependencies=dependencies,
            cpu_seconds=EXPECTED_PROBE_CPU_SECONDS[probe_id],
            wall_seconds=EXPECTED_PROBE_WALL_SECONDS[probe_id],
        )
        _verify_probe_result(
            probe_id,
            binding,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr_bytes,
        )
        ran += 1
    for source_path, (expected, maximum_bytes, label) in sorted(
        source_snapshots.items(),
        key=lambda item: item[0].as_posix(),
    ):
        current = read_bounded_regular_file(
            source_path,
            maximum_bytes=maximum_bytes,
            label=f"{label} stability check",
        )
        require_exact(current, expected, f"{label} changed during probe execution")
    return ran


def _least_privilege_resource_limit(
    *,
    requested_soft: int,
    requested_hard: int,
    inherited_soft: int,
    inherited_hard: int,
) -> tuple[int, int]:
    """Return a child limit that cannot relax either inherited limit."""

    hard_bounds = [requested_hard]
    for inherited_bound in (inherited_soft, inherited_hard):
        if inherited_bound != resource.RLIM_INFINITY:
            hard_bounds.append(inherited_bound)
    bounded_hard = min(hard_bounds)
    return min(requested_soft, bounded_hard), bounded_hard


def _limit_probe_child_resources(*, cpu_seconds: int) -> None:
    """Install portable kernel limits before the fixed probe loader starts."""

    def install(resource_id: int, soft: int, hard: int) -> None:
        inherited_soft, inherited_hard = resource.getrlimit(resource_id)
        # The probe must not regain authority that its caller removed. Bound the
        # new hard limit by the inherited soft limit as well as the inherited
        # hard limit, so probe code cannot raise a stricter inherited soft limit.
        resource.setrlimit(
            resource_id,
            _least_privilege_resource_limit(
                requested_soft=soft,
                requested_hard=hard,
                inherited_soft=inherited_soft,
                inherited_hard=inherited_hard,
            ),
        )

    install(
        resource.RLIMIT_FSIZE,
        MAX_PROBE_OUTPUT_BYTES,
        MAX_PROBE_OUTPUT_BYTES,
    )
    install(resource.RLIMIT_CORE, 0, 0)
    install(
        resource.RLIMIT_NOFILE,
        MAX_PROBE_OPEN_FILES,
        MAX_PROBE_OPEN_FILES,
    )
    install(
        resource.RLIMIT_CPU,
        cpu_seconds,
        cpu_seconds + 1,
    )


def _build_probe_frame(
    script_bytes: bytes,
    *,
    probe_id: str,
    script_path: str = "<bound-probe>",
    dependencies: tuple[tuple[str, str, bytes], ...] = (),
) -> bytes:
    """Validate and frame one exact script and its ordered source closure."""

    require(
        type(probe_id) is str
        and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", probe_id) is not None,
        "bounded probe ID is invalid",
    )
    require(
        type(script_path) is str and "\x00" not in script_path,
        f"{probe_id}: script path is invalid",
    )
    require(
        type(script_bytes) is bytes and 0 < len(script_bytes) <= MAX_PROBE_SCRIPT_BYTES,
        f"{probe_id}: script bytes exceed their exact bound",
    )
    require(
        type(dependencies) is tuple and len(dependencies) <= MAX_PROBE_DEPENDENCIES,
        f"{probe_id}: dependency count exceeds its exact bound",
    )
    module_names: set[str] = set()
    frame = bytearray(PROBE_FRAME_MAGIC)
    frame.extend(len(dependencies).to_bytes(2, "big"))

    def append_text(value: str, *, maximum: int, label: str) -> None:
        require(
            type(value) is str and "\x00" not in value,
            f"{probe_id}: {label} is invalid",
        )
        try:
            raw = value.encode("utf-8")
        except UnicodeError as error:
            fail(f"{probe_id}: {label} is not UTF-8: {error}")
        require(
            0 < len(raw) <= maximum,
            f"{probe_id}: {label} exceeds its exact bound",
        )
        frame.extend(len(raw).to_bytes(2, "big"))
        frame.extend(raw)

    for dependency in dependencies:
        require(
            type(dependency) is tuple and len(dependency) == 3,
            f"{probe_id}: dependency frame shape is invalid",
        )
        module_name, dependency_path, dependency_bytes = dependency
        require(
            type(module_name) is str
            and module_name.isascii()
            and module_name.isidentifier()
            and len(module_name) <= MAX_PROBE_MODULE_NAME_BYTES
            and module_name not in module_names,
            f"{probe_id}: dependency module is invalid or duplicated",
        )
        require(
            type(dependency_bytes) is bytes
            and 0 < len(dependency_bytes) <= MAX_PROBE_DEPENDENCY_BYTES,
            f"{probe_id}: dependency bytes exceed their exact bound",
        )
        module_names.add(module_name)
        append_text(
            module_name,
            maximum=MAX_PROBE_MODULE_NAME_BYTES,
            label="dependency module",
        )
        append_text(
            dependency_path,
            maximum=MAX_PROBE_SOURCE_PATH_BYTES,
            label="dependency path",
        )
        frame.extend(len(dependency_bytes).to_bytes(4, "big"))
        frame.extend(dependency_bytes)
    append_text(
        script_path,
        maximum=MAX_PROBE_SOURCE_PATH_BYTES,
        label="script path",
    )
    frame.extend(len(script_bytes).to_bytes(4, "big"))
    frame.extend(script_bytes)
    require(
        len(frame) <= MAX_PROBE_INPUT_BYTES,
        f"{probe_id}: aggregate framed input exceeds its exact bound",
    )
    return bytes(frame)


def _terminate_probe_process_group(process: subprocess.Popen[bytes]) -> None:
    """Kill and reap the exact fresh-session probe group."""

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        if process.poll() is None:
            process.kill()
    process.communicate()


def _communicate_with_probe_cleanup(
    process: subprocess.Popen[bytes],
    *,
    frame: bytes,
    probe_id: str,
    cpu_seconds: int,
    wall_seconds: int,
) -> None:
    """Communicate with one probe and reap its group on every exceptional exit."""

    try:
        process.communicate(input=frame, timeout=wall_seconds)
    except subprocess.TimeoutExpired:
        _terminate_probe_process_group(process)
        fail(
            f"{probe_id}: command exceeded {wall_seconds} wall-clock seconds "
            f"with a {cpu_seconds}-second CPU limit"
        )
    except BaseException:
        _terminate_probe_process_group(process)
        raise


def _run_probe_frame(
    frame: bytes,
    *,
    probe_id: str,
    cpu_seconds: int,
    wall_seconds: int,
) -> tuple[int, bytes, bytes]:
    """Run one bounded raw frame in the fixed loader."""

    require(
        type(cpu_seconds) is int and 0 < cpu_seconds <= MAX_PROBE_CPU_SECONDS,
        f"{probe_id}: invalid bounded CPU limit",
    )
    require(
        type(wall_seconds) is int
        and cpu_seconds <= wall_seconds <= MAX_PROBE_WALL_SECONDS,
        f"{probe_id}: invalid bounded wall limit",
    )
    require(
        type(probe_id) is str
        and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", probe_id) is not None,
        "bounded probe ID is invalid",
    )
    require(
        type(frame) is bytes and 0 < len(frame) <= MAX_PROBE_INPUT_BYTES,
        f"{probe_id}: raw frame exceeds its exact bound",
    )

    with tempfile.TemporaryDirectory(prefix="ncp-bound-probe-") as probe_cwd:
        with tempfile.TemporaryFile(mode="w+b") as stdout_file:
            with tempfile.TemporaryFile(mode="w+b") as stderr_file:
                try:
                    process = subprocess.Popen(  # noqa: S603
                        [
                            sys.executable,
                            "-I",
                            "-S",
                            "-B",
                            "-X",
                            "utf8",
                            "-c",
                            PROBE_LOADER_SOURCE,
                        ],
                        cwd=probe_cwd,
                        env={"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
                        stdin=subprocess.PIPE,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        start_new_session=True,
                        preexec_fn=partial(
                            _limit_probe_child_resources,
                            cpu_seconds=cpu_seconds,
                        ),
                    )
                except (OSError, subprocess.SubprocessError) as error:
                    fail(f"{probe_id}: cannot start bounded probe: {error}")
                _communicate_with_probe_cleanup(
                    process,
                    frame=frame,
                    probe_id=probe_id,
                    cpu_seconds=cpu_seconds,
                    wall_seconds=wall_seconds,
                )
                stdout_file.seek(0)
                stderr_file.seek(0)
                stdout = stdout_file.read(MAX_PROBE_OUTPUT_BYTES + 1)
                stderr = stderr_file.read(MAX_PROBE_OUTPUT_BYTES + 1)
    require(
        len(stdout) <= MAX_PROBE_OUTPUT_BYTES,
        f"{probe_id}: stdout exceeds {MAX_PROBE_OUTPUT_BYTES} bytes",
    )
    require(
        len(stderr) <= MAX_PROBE_OUTPUT_BYTES,
        f"{probe_id}: stderr exceeds {MAX_PROBE_OUTPUT_BYTES} bytes",
    )
    return process.returncode, stdout, stderr


def _run_bounded_probe(
    script_bytes: bytes,
    *,
    probe_id: str,
    script_path: str = "<bound-probe>",
    dependencies: tuple[tuple[str, str, bytes], ...] = (),
    cpu_seconds: int = PROBE_SELF_TEST_CPU_SECONDS,
    wall_seconds: int = PROBE_SELF_TEST_WALL_SECONDS,
) -> tuple[int, bytes, bytes]:
    """Execute exact bytes in a bounded loader without repository cwd access."""

    frame = _build_probe_frame(
        script_bytes,
        probe_id=probe_id,
        script_path=script_path,
        dependencies=dependencies,
    )
    return _run_probe_frame(
        frame,
        probe_id=probe_id,
        cpu_seconds=cpu_seconds,
        wall_seconds=wall_seconds,
    )


def _run_probe_loader_self_test() -> int:
    """Exercise framing, isolation, bounds, ordering, and least privilege."""

    checks = 0
    for label, cpu_seconds, wall_seconds in (
        ("zero-wall", 1, 0),
        ("wall-below-cpu", 2, 1),
        ("cpu-over-maximum", MAX_PROBE_CPU_SECONDS + 1, MAX_PROBE_WALL_SECONDS),
        ("wall-over-maximum", 1, MAX_PROBE_WALL_SECONDS + 1),
    ):
        try:
            _run_probe_frame(
                b"invalid-limit-frame",
                probe_id=f"{label}-loader-self-test",
                cpu_seconds=cpu_seconds,
                wall_seconds=wall_seconds,
            )
        except ClosureCheckError:
            checks += 1
        else:
            fail(f"probe loader accepted an invalid {label} limit pair")

    infinity = resource.RLIM_INFINITY
    limit_cases = (
        ((64, 64, infinity, infinity), (64, 64)),
        ((64, 64, 32, 256), (32, 32)),
        ((5, 6, 2, 100), (2, 2)),
        ((64, 64, infinity, 16), (16, 16)),
        ((64, 64, 8, infinity), (8, 8)),
        ((64, 64, 0, 256), (0, 0)),
    )
    for inputs, expected in limit_cases:
        require_exact(
            _least_privilege_resource_limit(
                requested_soft=inputs[0],
                requested_hard=inputs[1],
                inherited_soft=inputs[2],
                inherited_hard=inputs[3],
            ),
            expected,
            "probe loader least-privilege resource limit",
        )
        checks += 1

    exact_script = b"#" + b" " * (MAX_PROBE_SCRIPT_BYTES - 1)
    exact_dependency = b"#" + b" " * (MAX_PROBE_DEPENDENCY_BYTES - 1)
    maximum_frame = _build_probe_frame(
        exact_script,
        probe_id="maximum-frame-self-test",
        script_path="s" * MAX_PROBE_SOURCE_PATH_BYTES,
        dependencies=tuple(
            (
                "m" * (MAX_PROBE_MODULE_NAME_BYTES - 1) + str(index),
                str(index) + "p" * (MAX_PROBE_SOURCE_PATH_BYTES - 1),
                exact_dependency,
            )
            for index in range(MAX_PROBE_DEPENDENCIES)
        ),
    )
    require_exact(
        len(maximum_frame),
        MAX_PROBE_INPUT_BYTES,
        "probe loader aggregate exact bound",
    )
    checks += 1
    for label, oversized_script, oversized_dependencies in (
        (
            "script",
            exact_script + b" ",
            (),
        ),
        (
            "dependency",
            b"pass\n",
            (("oversized_dependency", "oversized.py", exact_dependency + b" "),),
        ),
    ):
        try:
            _build_probe_frame(
                oversized_script,
                probe_id=f"oversized-{label}-self-test",
                dependencies=oversized_dependencies,
            )
        except ClosureCheckError:
            checks += 1
        else:
            fail(f"probe loader accepted a one-byte-over {label}")
    try:
        _build_probe_frame(
            b"pass\n",
            probe_id="invalid-unicode-path-self-test",
            script_path="bad\ud800",
        )
    except ClosureCheckError:
        checks += 1
    else:
        fail("probe loader accepted an invalid-Unicode script path")

    ordered_returncode, ordered_stdout, ordered_stderr = _run_bounded_probe(
        (
            b"import sys\n"
            b"from loader_second import VALUE\n"
            b"assert VALUE == 42\n"
            b"assert sys.modules['__main__'].__dict__ is globals()\n"
            b"print('SCRIPT')\n"
        ),
        probe_id="ordered-loader-self-test",
        script_path="ordered-script.py",
        dependencies=(
            ("loader_first", "loader-first.py", b"VALUE = 41\nprint('FIRST')\n"),
            (
                "loader_second",
                "loader-second.py",
                b"from loader_first import VALUE\nVALUE += 1\nprint('SECOND')\n",
            ),
        ),
    )
    require_exact(ordered_returncode, 0, "ordered probe loader return code")
    require_exact(
        ordered_stdout,
        b"FIRST\nSECOND\nSCRIPT\n",
        "ordered probe loader stdout",
    )
    require_exact(ordered_stderr, b"", "ordered probe loader stderr")
    checks += 1

    isolation_returncode, isolation_stdout, isolation_stderr = _run_bounded_probe(
        (
            b"import os\n"
            b"import sys\n"
            b"assert os.environ == {}\n"
            b"assert os.listdir('.') == []\n"
            b"assert '' not in sys.path and os.getcwd() not in sys.path\n"
            b"assert sys.flags.isolated == 1\n"
            b"assert sys.flags.no_site == 1\n"
            b"assert sys.flags.dont_write_bytecode == 1\n"
            b"assert sys.flags.utf8_mode == 1\n"
            b"try:\n"
            b"    import selector_closure_codec\n"
            b"except ModuleNotFoundError:\n"
            b"    pass\n"
            b"else:\n"
            b"    raise AssertionError('repository import remained reachable')\n"
            b"print('ISOLATED')\n"
        ),
        probe_id="isolation-loader-self-test",
    )
    require_exact(isolation_returncode, 0, "isolated probe loader return code")
    require_exact(isolation_stdout, b"ISOLATED\n", "isolated probe loader stdout")
    require_exact(isolation_stderr, b"", "isolated probe loader stderr")
    checks += 1

    side_effect_dependency = (
        "side_effect_dependency",
        "side-effect.py",
        b"print('DEPENDENCY_EXECUTED')\n",
    )
    complete_frame = _build_probe_frame(
        b"print('SCRIPT_EXECUTED')\n",
        probe_id="parse-before-execute-self-test",
        dependencies=(side_effect_dependency,),
    )
    malformed_frames = (
        ("truncated", complete_frame[:-1], b"truncated probe frame"),
        ("trailing", complete_frame + b"x", b"probe frame has trailing bytes"),
        (
            "later-syntax",
            _build_probe_frame(
                b"this is not valid Python =\n",
                probe_id="syntax-before-execute-self-test",
                dependencies=(side_effect_dependency,),
            ),
            b"SyntaxError",
        ),
    )
    for label, frame, diagnostic in malformed_frames:
        returncode, stdout, stderr = _run_probe_frame(
            frame,
            probe_id=f"{label}-frame-self-test",
            cpu_seconds=PROBE_SELF_TEST_CPU_SECONDS,
            wall_seconds=PROBE_SELF_TEST_WALL_SECONDS,
        )
        require(returncode != 0, f"probe loader accepted a {label} frame")
        require_exact(
            stdout,
            b"",
            f"probe loader executed a dependency before rejecting {label}",
        )
        require(
            diagnostic in stderr,
            f"probe loader {label} diagnostic differs",
        )
        checks += 1

    collision_returncode, collision_stdout, collision_stderr = _run_bounded_probe(
        b"print('SCRIPT_EXECUTED')\n",
        probe_id="module-collision-self-test",
        dependencies=(("os", "collision.py", b"print('DEPENDENCY_EXECUTED')\n"),),
    )
    require(collision_returncode != 0, "probe loader accepted a module collision")
    require_exact(
        collision_stdout,
        b"",
        "probe loader executed source before rejecting a module collision",
    )
    require(
        b"probe dependency module name is invalid" in collision_stderr,
        "probe loader module-collision diagnostic differs",
    )
    checks += 1

    class InterruptedProbeProcess:
        def communicate(self, *, input: bytes, timeout: int) -> None:
            require_exact(input, b"interrupt", "interrupted probe frame")
            require_exact(timeout, 2, "interrupted probe wall limit")
            raise KeyboardInterrupt

    interrupted_process = InterruptedProbeProcess()
    cleaned_processes: list[object] = []
    original_terminator = globals()["_terminate_probe_process_group"]
    globals()["_terminate_probe_process_group"] = cleaned_processes.append
    try:
        try:
            _communicate_with_probe_cleanup(
                interrupted_process,  # type: ignore[arg-type]
                frame=b"interrupt",
                probe_id="interrupt-cleanup-self-test",
                cpu_seconds=1,
                wall_seconds=2,
            )
        except KeyboardInterrupt:
            pass
        else:
            fail("probe communication swallowed caller interruption")
    finally:
        globals()["_terminate_probe_process_group"] = original_terminator
    require_exact(
        cleaned_processes,
        [interrupted_process],
        "interrupted probe process-group cleanup",
    )
    checks += 1

    try:
        timeout_returncode, _, _ = _run_bounded_probe(
            b"while True:\n    pass\n",
            probe_id="timeout-loader-self-test",
            cpu_seconds=1,
            wall_seconds=2,
        )
    except ClosureCheckError:
        checks += 1
    else:
        require(timeout_returncode != 0, "probe loader accepted an unbounded loop")
        checks += 1
    return checks


def run_hostile_self_test(source: Path) -> int:
    """Require semantic mutations to fail after commitments are refreshed."""

    from generate_selector_closure_source import _recompute_closure_commitments

    _run_semantic_validation_mode_self_test()
    _run_cli_validation_mode_self_test()
    _run_review_candidate_boundary_self_test()
    run_codec_self_test()
    resource_closure_codec_mutants = run_resource_closure_self_test()
    extraction_mutants = _run_adr_extraction_self_test()
    allocation_mutants = _run_allocation_coverage_self_test()
    profile_allocation_mutants = _run_structural_profile_allocation_self_test()
    artifact_allocation_identity_mutants = _run_artifact_allocation_identity_self_test()
    selector_resource_allocation_mutants = _run_selector_resource_allocation_self_test()
    artifact_registry_mutants = _run_artifact_registry_usage_self_test()
    owned_resource_registry_mutants = _run_owned_resource_registry_self_test()
    state_reachability_mutants = _run_domain_state_reachability_self_test()
    case_variant_write_role_mutants = _run_case_variant_write_role_closure_self_test()
    request_partition_mutants = _run_request_partition_contract_self_test()
    request_product_mutants = _run_request_product_liveness_self_test()
    request_causal_mutants = _run_request_causal_liveness_self_test()
    request_evidence_mutants = _run_request_evidence_contract_self_test()
    cross_store_manifest_mutants = _run_cross_store_publication_manifest_self_test()
    request_successor_mutants = _run_request_successor_contract_self_test()
    request_domain_mutants = _run_request_domain_contract_self_test()
    selector_root_domain_mutants = _run_selector_root_domain_contract_self_test()
    decision_relation_diagnostic_mutants = _run_decision_relation_coverage_self_test()
    shape_mutants = _run_semantic_shape_self_test()
    semantic_review_summary_mutants = _run_candidate_semantic_review_summary_self_test()
    source_envelope, baseline = load_compact_source(source)
    baseline = copy.deepcopy(baseline)
    validate_expanded_source(
        baseline,
        require_complete_allocation=False,
        allow_known_incomplete=True,
    )
    require_exact(
        run_bound_probes(baseline),
        len(EXPECTED_PROBE_REVIEW_COMMANDS),
        "hostile self-test baseline probe count",
    )
    probe_mutants = _run_probe_dependency_bound_self_test(baseline)
    probe_mutants += _run_probe_loader_self_test()
    closure_aggregation_mutants = _run_observer_grant_closure_aggregation_self_test(
        baseline
    )
    selector_extension_mutants = _run_selector_extension_contract_self_test(baseline)
    try:
        oversized_probe_returncode, _, _ = _run_bounded_probe(
            (
                b"import sys\n"
                b"sys.stdout.write('x' * "
                + str(MAX_PROBE_OUTPUT_BYTES + 1).encode("ascii")
                + b")\n"
            ),
            probe_id="oversized-output-self-test",
        )
    except ClosureCheckError:
        probe_mutants += 1
    else:
        require(
            oversized_probe_returncode != 0,
            "probe binding self-test accepted oversized stdout",
        )
        probe_mutants += 1
    try:
        _verify_probe_result(
            "stderr-self-test",
            {
                "stdout_byte_length": len(b"exact output\n"),
                "stdout_sha256": sha256(b"exact output\n").hexdigest(),
            },
            returncode=0,
            stdout=b"exact output\n",
            stderr=b"unexpected diagnostic\n",
        )
    except ClosureCheckError:
        probe_mutants += 1
    else:
        fail("probe binding self-test accepted successful execution with stderr")
    for label, key, value in (
        (
            "an unbound executable path",
            "review_command",
            "python3 prototypes/b01-architecture-evidence/unbound.py",
        ),
        (
            "an unknown binding property",
            "unknown_permissive_binding_property",
            True,
        ),
    ):
        hostile_probe = copy.deepcopy(baseline)
        hostile_probe["adversarial_probe_bindings"]["freshness_acceptance_probe"][
            key
        ] = value
        try:
            run_bound_probes(hostile_probe)
        except ClosureCheckError:
            probe_mutants += 1
        else:
            fail(f"probe binding self-test accepted {label}")
    legacy_binding_fields = {
        "freshness_acceptance_probe": {
            "accepted_cases",
            "invariants",
            "rejected_hostile_cases",
            "semantic_digest",
            "typed_artifacts",
        },
        "observer_authorization_probe": {
            "contrasts",
            "rejected_hostile_cases",
            "targeted_cases",
            "typed_artifacts",
            "witnesses",
        },
        "observer_capture_probe": {
            "contrasts",
            "rejected_hostile_cases",
            "targeted_cases",
            "typed_artifacts",
            "witnesses",
        },
        "source_issuance_index_probe": {
            "accepted_scenarios",
            "invariants",
            "rejected_hostile_cases",
            "semantic_digest",
            "typed_artifacts",
            "witnesses",
        },
    }
    original_probe_runner = _run_bounded_probe
    premature_legacy_probe_runner_calls: list[str] = []

    def record_legacy_probe_execution(
        _: bytes,
        *,
        probe_id: str,
        **__: Any,
    ) -> tuple[int, bytes, bytes]:
        premature_legacy_probe_runner_calls.append(probe_id)
        return 0, b"", b""

    globals()["_run_bounded_probe"] = record_legacy_probe_execution
    try:
        for probe_id, legacy_fields in sorted(legacy_binding_fields.items()):
            for legacy_field in sorted(legacy_fields):
                hostile_probe = {
                    "adversarial_probe_bindings": copy.deepcopy(
                        baseline["adversarial_probe_bindings"]
                    )
                }
                hostile_probe["adversarial_probe_bindings"][probe_id][legacy_field] = (
                    "0" * 64 if legacy_field == "semantic_digest" else 0
                )
                try:
                    run_bound_probes(hostile_probe)
                except ClosureCheckError:
                    probe_mutants += 1
                else:
                    fail(
                        f"{probe_id}: probe binding self-test accepted legacy "
                        f"metadata {legacy_field}"
                    )
    finally:
        globals()["_run_bounded_probe"] = original_probe_runner
    require(
        not premature_legacy_probe_runner_calls,
        "probe binding self-test executed a script before rejecting legacy metadata",
    )
    hostile_claim = copy.deepcopy(baseline)
    hostile_claim["adversarial_probe_bindings"]["claim_boundary"] += "_CHANGED"
    try:
        run_bound_probes(hostile_claim)
    except ClosureCheckError:
        probe_mutants += 1
    else:
        fail("probe binding self-test accepted a changed claim boundary")
    dependency_binding_mutations: tuple[
        tuple[str, tuple[str, ...], Any],
        ...,
    ] = (
        (
            "a changed canonical-source digest",
            (
                "shared_source_bindings",
                "bounded_canonical",
                "sha256",
            ),
            "0" * 64,
        ),
        (
            "a substituted bounded-JSON path",
            (
                "shared_source_bindings",
                "bounded_json",
                "path",
            ),
            "prototypes/b01-architecture-evidence/bounded_json.py",
        ),
        (
            "a changed shared-source digest",
            (
                "shared_source_bindings",
                "observer_read_capture_bridge",
                "sha256",
            ),
            "0" * 64,
        ),
        (
            "a changed shared-source byte length",
            (
                "shared_source_bindings",
                "observer_read_capture_bridge",
                "byte_length",
            ),
            (
                baseline["adversarial_probe_bindings"]["shared_source_bindings"][
                    "observer_read_capture_bridge"
                ]["byte_length"]
                + 1
            ),
        ),
        (
            "an over-limit shared-source byte length",
            (
                "shared_source_bindings",
                "observer_read_capture_bridge",
                "byte_length",
            ),
            MAX_PROBE_DEPENDENCY_BYTES + 1,
        ),
        (
            "a substituted shared-source module",
            (
                "shared_source_bindings",
                "observer_read_capture_bridge",
                "module",
            ),
            "observer_read_capture_bridge_substitute",
        ),
        (
            "a substituted shared-source path",
            (
                "shared_source_bindings",
                "observer_read_capture_bridge",
                "path",
            ),
            ("prototypes/b01-architecture-evidence/observer_authorization_probe.py"),
        ),
        (
            "an omitted bridge direct dependency",
            (
                "shared_source_bindings",
                "observer_read_capture_bridge",
                "dependency_ids",
            ),
            [],
        ),
        (
            "an omitted authorization dependency",
            ("observer_authorization_probe", "dependency_ids"),
            ["bounded_json", "observer_read_capture_bridge"],
        ),
        (
            "a reordered authorization dependency closure",
            ("observer_authorization_probe", "dependency_ids"),
            [
                "observer_read_capture_bridge",
                "bounded_canonical",
                "bounded_json",
            ],
        ),
        (
            "an omitted capture transitive dependency",
            ("observer_capture_probe", "dependency_ids"),
            ["observer_read_capture_bridge"],
        ),
        (
            "an unknown capture dependency",
            ("observer_capture_probe", "dependency_ids"),
            ["observer_read_capture_bridge_substitute"],
        ),
    )
    premature_dependency_probe_runner_calls: list[str] = []

    def record_dependency_probe_execution(
        _: bytes,
        *,
        probe_id: str,
        **__: Any,
    ) -> tuple[int, bytes, bytes]:
        premature_dependency_probe_runner_calls.append(probe_id)
        return 0, b"", b""

    globals()["_run_bounded_probe"] = record_dependency_probe_execution
    try:
        for label, key_path, value in dependency_binding_mutations:
            hostile_dependency = copy.deepcopy(baseline)
            cursor = hostile_dependency["adversarial_probe_bindings"]
            for key_part in key_path[:-1]:
                cursor = cursor[key_part]
            cursor[key_path[-1]] = value
            try:
                run_bound_probes(hostile_dependency)
            except ClosureCheckError:
                probe_mutants += 1
            else:
                fail(f"probe binding self-test accepted {label}")
    finally:
        globals()["_run_bounded_probe"] = original_probe_runner
    require(
        not premature_dependency_probe_runner_calls,
        "probe binding self-test executed a script before rejecting a dependency "
        "binding mutation",
    )
    hostile_script_digest = copy.deepcopy(baseline)
    hostile_script_digest["adversarial_probe_bindings"]["freshness_acceptance_probe"][
        "script_sha256"
    ] = "0" * 64
    premature_probe_runner_calls: list[str] = []

    def record_premature_probe_execution(
        _: bytes,
        *,
        probe_id: str,
        **__: Any,
    ) -> tuple[int, bytes, bytes]:
        premature_probe_runner_calls.append(probe_id)
        return 0, b"", b""

    globals()["_run_bounded_probe"] = record_premature_probe_execution
    script_digest_rejected = False
    try:
        try:
            run_bound_probes(hostile_script_digest)
        except ClosureCheckError:
            script_digest_rejected = True
    finally:
        globals()["_run_bounded_probe"] = original_probe_runner
    require(
        script_digest_rejected,
        "probe binding self-test accepted a changed script digest",
    )
    require(
        not premature_probe_runner_calls,
        "probe binding self-test executed a script before verifying its digest",
    )
    probe_mutants += 1
    for probe_id in sorted(EXPECTED_PROBE_REVIEW_COMMANDS):
        binding = baseline["adversarial_probe_bindings"][probe_id]
        script_path = Path(binding["source_path"])
        script_bytes = read_bounded_regular_file(
            ROOT / script_path,
            maximum_bytes=MAX_PROBE_SCRIPT_BYTES,
            label=f"{probe_id} same-output mutation source",
        )
        _verify_probe_script_binding(probe_id, binding, script_bytes)
        hostile_script_bytes = (
            script_bytes
            + b"\nif False:\n"
            + b"    raise RuntimeError('hidden same-output logic')\n"
        )
        dependency_sources = tuple(
            (
                baseline["adversarial_probe_bindings"]["shared_source_bindings"][
                    source_id
                ]["module"],
                baseline["adversarial_probe_bindings"]["shared_source_bindings"][
                    source_id
                ]["path"],
                read_bounded_regular_file(
                    ROOT
                    / baseline["adversarial_probe_bindings"]["shared_source_bindings"][
                        source_id
                    ]["path"],
                    maximum_bytes=MAX_PROBE_DEPENDENCY_BYTES,
                    label=f"{probe_id} same-output dependency source",
                ),
            )
            for source_id in binding["dependency_ids"]
        )
        returncode, stdout, stderr = _run_bounded_probe(
            hostile_script_bytes,
            probe_id=f"{probe_id}-same-output-mutant",
            script_path=script_path.as_posix(),
            dependencies=dependency_sources,
            cpu_seconds=EXPECTED_PROBE_CPU_SECONDS[probe_id],
            wall_seconds=EXPECTED_PROBE_WALL_SECONDS[probe_id],
        )
        require_exact(
            returncode,
            0,
            f"{probe_id}: same-output mutant return code",
        )
        require_exact(
            sha256(stdout).hexdigest(),
            binding["stdout_sha256"],
            f"{probe_id}: same-output mutant stdout digest",
        )
        require_exact(
            stderr,
            b"",
            f"{probe_id}: same-output mutant stderr",
        )
        try:
            _verify_probe_script_binding(
                probe_id,
                binding,
                hostile_script_bytes,
            )
        except ClosureCheckError:
            probe_mutants += 1
        else:
            fail(
                f"{probe_id}: probe binding self-test accepted hidden same-output logic"
            )
    for document_index, document in enumerate(
        baseline["adr_allocation_oracle"]["documents"]
    ):
        document.pop("allocation_identifier_count", None)
        document.pop("allocation_identifier_sha256", None)
        raw = read_bounded_regular_file(
            ROOT / document["path"],
            maximum_bytes=MAX_ADR_BYTES,
            label=f"{document['adr_id']} self-test allocation source",
        )
        document["byte_length"] = len(raw)
        document["sha256"] = sha256(raw).hexdigest()
        document["modules"] = []
        for module_index, module_path in enumerate(
            ADR_ALLOCATION_MODULE_PATHS[document_index]
        ):
            module_raw = read_bounded_regular_file(
                ROOT / module_path,
                maximum_bytes=MAX_ADR_BYTES,
                label=(
                    f"{document['adr_id']} self-test allocation module {module_index}"
                ),
            )
            document["modules"].append(
                {
                    "byte_length": len(module_raw),
                    "path": module_path,
                    "sha256": sha256(module_raw).hexdigest(),
                }
            )
        document["source_set"] = copy.deepcopy(ADR_SOURCE_SET_SUITE)
        document["source_set"]["sha256"] = adr_source_set_sha256(
            adr_id=document["adr_id"],
            path=document["path"],
            byte_length=document["byte_length"],
            source_sha256=document["sha256"],
            modules=document["modules"],
        )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            fail(
                f"{document['adr_id']} self-test allocation source: "
                f"invalid UTF-8: {error}"
            )
        anchor_id = ADR_ALLOCATION_ANCHOR_BY_ID[document["adr_id"]]
        document["allocation_anchor_id"] = _extract_allocation_anchor(
            text,
            expected_anchor_id=anchor_id,
            label=document["adr_id"],
        )
        allocation_rows = [
            row
            for row in baseline["adr_allocation_oracle"]["allocations"]
            if row["adr_id"] == document["adr_id"]
        ]
        exclusion_rows = [
            row
            for row in baseline["adr_allocation_oracle"]["exclusions"]
            if row["adr_id"] == document["adr_id"]
        ]
        document["allocation_row_count"] = len(allocation_rows)
        document["allocation_rows_sha256"] = document_rows_sha256(
            allocation_rows,
            row_kind="allocations",
        )
        document["exclusion_row_count"] = len(exclusion_rows)
        document["exclusion_rows_sha256"] = document_rows_sha256(
            exclusion_rows,
            row_kind="exclusions",
        )
    baseline["adr_allocation_oracle"]["document_row_commitment"] = copy.deepcopy(
        DOCUMENT_ROW_COMMITMENT
    )
    baseline["adr_allocation_oracle"]["provenance_review"] = (
        build_not_reviewed_provenance_review()
    )
    _recompute_closure_commitments(baseline)
    validate_expanded_source(
        baseline,
        require_complete_allocation=False,
        allow_known_incomplete=True,
    )
    try:
        validate_expanded_source(baseline)
    except ClosureCheckError as error:
        require(
            "ADR allocation oracle is incomplete" in str(error),
            f"unexpected fail-closed baseline reason: {error}",
        )
    else:
        fail("stale selector model unexpectedly passed the allocation oracle")

    mutations: list[tuple[str, Any]] = []

    def mutate_scalar_with_all_legacy_review_metrics_unchanged(
        data: dict[str, Any],
    ) -> None:
        model_before = _model_allocations(data)
        shape_before = _semantic_shape_commitment(data)
        subject_before = semantic_review_subject_commitment(data)
        data["allocation_boundary"] += " scalar-review-subject-hostile-mutation"
        require_exact(
            _model_allocations(data),
            model_before,
            "scalar-review hostile model allocations",
        )
        require_exact(
            _semantic_shape_commitment(data),
            shape_before,
            "scalar-review hostile semantic shape",
        )
        require(
            semantic_review_subject_commitment(data) != subject_before,
            "semantic review subject ignored a scalar-only semantic mutation",
        )

    mutations.append(
        (
            "scalar semantic mutation with unchanged model rows and shape",
            mutate_scalar_with_all_legacy_review_metrics_unchanged,
        )
    )

    def mutate_unknown_top(data: dict[str, Any]) -> None:
        data["unknown_permissive_top_level"] = True

    mutations.append(("unknown top-level property", mutate_unknown_top))

    def mutate_unknown_selector(data: dict[str, Any]) -> None:
        data["selectors"][0]["unknown_permissive_selector_property"] = True

    mutations.append(("unknown selector property", mutate_unknown_selector))

    def mutate_unknown_event(data: dict[str, Any]) -> None:
        data["selectors"][0]["events"][0]["unknown_permissive_event_property"] = True

    mutations.append(("unknown event property", mutate_unknown_event))

    def mutate_unknown_decision_axis(data: dict[str, Any]) -> None:
        data["selectors"][0]["events"][0]["decision_model"]["axes"][0][
            "unknown_permissive_axis_property"
        ] = True

    mutations.append(("unknown decision-axis property", mutate_unknown_decision_axis))

    def mutate_unknown_truth_condition(data: dict[str, Any]) -> None:
        data["selectors"][0]["events"][0]["decision_model"][
            "evidence_variant_definitions"
        ][0]["truth_conditions"][0]["unknown_permissive_truth_property"] = True

    mutations.append(
        (
            "unknown evidence truth-condition property",
            mutate_unknown_truth_condition,
        )
    )

    def mutate_unknown_nested_profile(data: dict[str, Any]) -> None:
        data["security_authority_state_profile"][
            "unknown_permissive_nested_profile_property"
        ] = True
        shape_count, shape_digest = _semantic_shape_commitment(data)
        data["adr_allocation_oracle"]["semantic_shape_entry_count"] = shape_count
        data["adr_allocation_oracle"]["semantic_shape_sha256"] = shape_digest

    mutations.append(("unknown nested profile property", mutate_unknown_nested_profile))

    def mutate_dangling_guard(data: dict[str, Any]) -> None:
        data["selectors"][0]["events"][0]["guards_profile_ref"] = (
            "GUARDS_PROFILE_DOES_NOT_EXIST"
        )

    mutations.append(("dangling guard profile", mutate_dangling_guard))

    def mutate_unused_closed_event_profile(data: dict[str, Any]) -> None:
        unused = copy.deepcopy(data["closed_event_profile_catalog"]["guards"][0])
        unused["profile_id"] = "GUARDS_PROFILE_UNUSED"
        data["closed_event_profile_catalog"]["guards"].append(unused)
        model = _model_allocations(data)
        data["adr_allocation_oracle"]["model_allocation_count"] = len(model)
        data["adr_allocation_oracle"]["model_allocation_sha256"] = (
            _model_allocation_sha256(model)
        )
        shape_count, shape_digest = _semantic_shape_commitment(data)
        data["adr_allocation_oracle"]["semantic_shape_entry_count"] = shape_count
        data["adr_allocation_oracle"]["semantic_shape_sha256"] = shape_digest

    mutations.append(
        ("unused closed-event profile definition", mutate_unused_closed_event_profile)
    )

    def mutate_unused_edge(data: dict[str, Any]) -> None:
        selector = data["selectors"][0]
        extra = copy.deepcopy(selector["state_edge_catalog"][0])
        extra["edge_id"] = "E999999"
        selector["state_edge_catalog"].append(extra)

    mutations.append(("unused state edge", mutate_unused_edge))

    def mutate_unreferenced_state(data: dict[str, Any]) -> None:
        states = data["selectors"][0]["state_domains"][0]["states"]
        states.append("UNKNOWN_PERMISSIVE")
        states.sort()

    mutations.append(("unreferenced state", mutate_unreferenced_state))

    def mutate_empty_terminal_set(data: dict[str, Any]) -> None:
        security = next(
            selector
            for selector in data["selectors"]
            if selector["selector_id"] == "SECURITY_AUTHORITY"
        )
        security["state_domains"][0]["terminal_states"] = []

    mutations.append(("unauthorized empty terminal set", mutate_empty_terminal_set))

    def mutate_terminality_policy(data: dict[str, Any]) -> None:
        data["selectors"][0]["state_domains"][0]["terminality"] = (
            "UNKNOWN_PERMISSIVE_TERMINALITY"
        )

    mutations.append(
        ("unknown permissive terminality policy", mutate_terminality_policy)
    )

    def mutate_reverse_partition(data: dict[str, Any]) -> None:
        for selector in data["selectors"]:
            for event in selector["events"]:
                case_ids = [
                    case["semantic_case_id"] for case in event["transition_cases"]
                ]
                for partition in event["partition_effects"]:
                    extra = next(
                        (
                            case_id
                            for case_id in case_ids
                            if case_id not in partition["applies_to_semantic_case_ids"]
                        ),
                        None,
                    )
                    if extra is not None:
                        partition["applies_to_semantic_case_ids"].append(extra)
                        return
        fail("self-test fixture lacks a reversible partition")

    mutations.append(("reverse-only partition applicability", mutate_reverse_partition))

    def mutate_cross_event_transition_kind(data: dict[str, Any]) -> None:
        for selector in data["selectors"]:
            if len(selector["events"]) >= 2:
                selector["events"][0]["transition_kind"] = selector["events"][1][
                    "transition_kind"
                ]
                return
        fail("self-test fixture lacks two events")

    mutations.append(
        ("cross-event transition kind", mutate_cross_event_transition_kind)
    )

    def mutate_transition_domain(data: dict[str, Any]) -> None:
        data["selectors"][0]["events"][0]["transition_kind_state_domain"] = (
            "UNKNOWN_STATE_DOMAIN"
        )

    mutations.append(("unknown transition state domain", mutate_transition_domain))

    def mutate_duplicate_consume(data: dict[str, Any]) -> None:
        event = data["selectors"][0]["events"][0]
        event["consumes"].append(copy.deepcopy(event["consumes"][0]))

    mutations.append(("duplicate consume role and artifact", mutate_duplicate_consume))

    def mutate_duplicate_evidence_variant(data: dict[str, Any]) -> None:
        for selector in data["selectors"]:
            for event in selector["events"]:
                variants = event["decision_model"]["evidence_variant_definitions"]
                if variants:
                    variants.append(copy.deepcopy(variants[0]))
                    return
        fail("self-test fixture lacks an evidence variant")

    mutations.append(("duplicate evidence variant", mutate_duplicate_evidence_variant))

    def mutate_required_forbidden_evidence_overlap(
        data: dict[str, Any],
    ) -> None:
        variant = data["selectors"][0]["events"][0]["decision_model"][
            "evidence_variant_definitions"
        ][0]
        variant["forbidden_fields"].append(
            data["selectors"][0]["events"][0]["decision_model"][
                "common_required_fields"
            ][0]
        )

    mutations.append(
        (
            "required and forbidden evidence overlap",
            mutate_required_forbidden_evidence_overlap,
        )
    )

    def mutate_duplicate_truth_condition(data: dict[str, Any]) -> None:
        truth_conditions = data["selectors"][0]["events"][0]["decision_model"][
            "evidence_variant_definitions"
        ][0]["truth_conditions"]
        truth_conditions.append(copy.deepcopy(truth_conditions[0]))

    mutations.append(
        ("duplicate evidence truth condition", mutate_duplicate_truth_condition)
    )

    def mutate_deadline_comparison(data: dict[str, Any]) -> None:
        for selector in data["selectors"]:
            for event in selector["events"]:
                conditions = event["deadline_conditions"]["conditions"]
                if conditions:
                    conditions[0]["comparison"] = "PERMISSIVE_IF_CLOCK_UNKNOWN"
                    return
        fail("self-test fixture lacks a deadline condition")

    mutations.append(("invalid deadline comparison", mutate_deadline_comparison))

    def mutate_adr_hash(data: dict[str, Any]) -> None:
        data["adr_allocation_oracle"]["documents"][0]["sha256"] = "0" * 64

    mutations.append(("stale ADR digest", mutate_adr_hash))

    def refresh_document_source_set(document: dict[str, Any]) -> None:
        document["source_set"] = copy.deepcopy(ADR_SOURCE_SET_SUITE)
        document["source_set"]["sha256"] = adr_source_set_sha256(
            adr_id=document["adr_id"],
            path=document["path"],
            byte_length=document["byte_length"],
            source_sha256=document["sha256"],
            modules=document["modules"],
        )

    def mutate_missing_adr_module(data: dict[str, Any]) -> None:
        document = data["adr_allocation_oracle"]["documents"][3]
        document["modules"].clear()
        refresh_document_source_set(document)

    mutations.append(("missing ADR module", mutate_missing_adr_module))

    def mutate_swapped_adr_modules(data: dict[str, Any]) -> None:
        documents = data["adr_allocation_oracle"]["documents"]
        left = copy.deepcopy(documents[3]["modules"])
        right = copy.deepcopy(documents[8]["modules"])
        documents[3]["modules"] = right
        documents[8]["modules"] = left
        refresh_document_source_set(documents[3])
        refresh_document_source_set(documents[8])

    mutations.append(("swapped ADR modules", mutate_swapped_adr_modules))

    def mutate_duplicate_adr_module(data: dict[str, Any]) -> None:
        document = data["adr_allocation_oracle"]["documents"][3]
        document["modules"].append(copy.deepcopy(document["modules"][0]))
        refresh_document_source_set(document)

    mutations.append(("duplicate ADR module", mutate_duplicate_adr_module))

    def mutate_stale_adr_module(data: dict[str, Any]) -> None:
        document = data["adr_allocation_oracle"]["documents"][3]
        document["modules"][0]["sha256"] = "0" * 64
        refresh_document_source_set(document)

    mutations.append(("stale ADR module digest", mutate_stale_adr_module))

    def mutate_oversized_adr_module(data: dict[str, Any]) -> None:
        document = data["adr_allocation_oracle"]["documents"][3]
        document["modules"][0]["byte_length"] = MAX_ADR_BYTES + 1
        refresh_document_source_set(document)

    mutations.append(("oversized ADR module", mutate_oversized_adr_module))

    def mutate_adr_source_set_digest(data: dict[str, Any]) -> None:
        data["adr_allocation_oracle"]["documents"][3]["source_set"]["sha256"] = "0" * 64

    mutations.append(("stale ADR source-set digest", mutate_adr_source_set_digest))

    def mutate_adr_module_path_escape(data: dict[str, Any]) -> None:
        document = data["adr_allocation_oracle"]["documents"][3]
        document["modules"][0]["path"] = "../escaped-module.md"
        refresh_document_source_set(document)

    mutations.append(("ADR module path escape", mutate_adr_module_path_escape))

    def mutate_adr_module_alias(data: dict[str, Any]) -> None:
        document = data["adr_allocation_oracle"]["documents"][3]
        document["modules"][0]["path"] = document["path"]
        refresh_document_source_set(document)

    mutations.append(("ADR module path alias", mutate_adr_module_alias))

    def mutate_source_lineage_security_writer(data: dict[str, Any]) -> None:
        for selector in data["selectors"]:
            for event in selector["events"]:
                if event["event_id"] == (
                    "LOGICAL_SESSION_GENERATION_LINEAGE_GENESIS_FROM_SERVER_AUTHORITY"
                ):
                    contract = event["authority_transaction_contract"]
                    contract["write_roles"].append("LOCAL_SECURITY_ENFORCEMENT")
                    contract["participant_role_variants"][0]["write_roles"].append(
                        "LOCAL_SECURITY_ENFORCEMENT"
                    )
                    return
        fail("self-test fixture lacks source-lineage genesis")

    mutations.append(
        (
            "source-lineage local-security writer regression",
            mutate_source_lineage_security_writer,
        )
    )

    def mutate_joint_declared_writer_count(data: dict[str, Any]) -> None:
        profile = data["joint_selector_transaction_profiles"][
            "JTX_OBSERVER_TARGET_CHALLENGE"
        ]
        profile["declared_writing_participant_count"] -= 1

    mutations.append(
        (
            "joint transaction declared-writer count mismatch",
            mutate_joint_declared_writer_count,
        )
    )

    def mutate_joint_case_scope_widening(data: dict[str, Any]) -> None:
        event = next(
            item
            for item in next(
                selector
                for selector in data["selectors"]
                if selector["selector_id"] == "OBSERVER_AUTHORIZATION"
            )["events"]
            if item["event_id"] == "CANCEL_OBSERVER_GRANT_REQUEST_BEFORE_ACCEPTANCE"
        )
        event["joint_selector_transaction_semantic_case_ids"].append(
            "FROM_GRANT_REQUEST_FRESHNESS_SLOT_AVAILABLE__ROOT_ACTIVE_"
            "TO_GRANT_REQUEST_FRESHNESS_SLOT_CANCELED_UNUSED__ROOT_ACTIVE"
        )

    mutations.append(
        (
            "joint transaction semantic-case scope widening",
            mutate_joint_case_scope_widening,
        )
    )

    def mutate_source_enrollment_removed(data: dict[str, Any]) -> None:
        source = next(
            selector
            for selector in data["selectors"]
            if selector["selector_id"] == "OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX"
        )
        source["events"] = [
            event
            for event in source["events"]
            if event["event_id"] != "ENROLL_OBSERVER_ROOT_IN_SOURCE_ISSUANCE_INDEX"
        ]

    mutations.append(
        (
            "source eligible-root enrollment event removed",
            mutate_source_enrollment_removed,
        )
    )

    def mutate_obsolete_hardware_alias(data: dict[str, Any]) -> None:
        data["allocation_boundary"] += (
            " physical-actuation-jurisdiction-hardware-install-"
            "authorization-type::"
            "PhysicalActuationJurisdictionHardwareInstallAuthorization"
        )

    mutations.append(
        ("obsolete hardware authorization alias", mutate_obsolete_hardware_alias)
    )

    def mutate_delete_model_event(data: dict[str, Any]) -> None:
        for selector in data["selectors"]:
            if selector["events"]:
                del selector["events"][0]
                model = _model_allocations(data)
                data["adr_allocation_oracle"]["model_allocation_count"] = len(model)
                data["adr_allocation_oracle"]["model_allocation_sha256"] = (
                    _model_allocation_sha256(model)
                )
                shape_count, shape_digest = _semantic_shape_commitment(data)
                data["adr_allocation_oracle"]["semantic_shape_entry_count"] = (
                    shape_count
                )
                data["adr_allocation_oracle"]["semantic_shape_sha256"] = shape_digest
                return
        fail("self-test fixture lacks a model event")

    mutations.append(("deleted model event", mutate_delete_model_event))

    killed = 0
    for label, mutate in mutations:
        hostile = copy.deepcopy(baseline)
        mutate(hostile)
        try:
            _recompute_closure_commitments(hostile)
        except ResourceClosureError:
            killed += 1
            continue
        try:
            validate_expanded_source(
                hostile,
                require_complete_allocation=False,
                allow_known_incomplete=True,
            )
        except ClosureCheckError:
            killed += 1
        else:
            fail(f"hostile self-test survived: {label}")
    _require_compact_source_unchanged(source, source_envelope)
    return (
        killed
        + extraction_mutants
        + allocation_mutants
        + profile_allocation_mutants
        + artifact_allocation_identity_mutants
        + selector_resource_allocation_mutants
        + artifact_registry_mutants
        + owned_resource_registry_mutants
        + resource_closure_codec_mutants
        + probe_mutants
        + shape_mutants
        + state_reachability_mutants
        + case_variant_write_role_mutants
        + request_partition_mutants
        + request_product_mutants
        + request_causal_mutants
        + request_evidence_mutants
        + cross_store_manifest_mutants
        + closure_aggregation_mutants
        + request_successor_mutants
        + request_domain_mutants
        + selector_root_domain_mutants
        + decision_relation_diagnostic_mutants
        + semantic_review_summary_mutants
        + selector_extension_mutants
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE,
        help="compact selector source",
    )
    parser.add_argument(
        "--run-probes",
        action="store_true",
        help="run and hash every bound adversarial probe",
    )
    parser.add_argument(
        "--probes-only",
        action="store_true",
        help="check bound probe output independently of semantic closure",
    )
    parser.add_argument(
        "--review-candidate",
        action="store_true",
        help=(
            "NON-GATING: require the exact "
            "INCOMPLETE_FAIL_CLOSED/NOT_REVIEWED/zero-digest boundary, "
            "relax allocation completeness only, and run full semantics plus "
            "every bound probe; this never completes B01 or authorizes release"
        ),
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run hostile parser and semantic mutation tests",
    )
    parser.add_argument(
        "--inventory-gap-report",
        action="store_true",
        help=(
            "emit a bounded read-only model/ADR inventory diagnostic; "
            "never allocate or freeze"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        mode = _cli_validation_mode(
            run_probes=args.run_probes,
            probes_only=args.probes_only,
            self_test=args.self_test,
            inventory_gap_report=args.inventory_gap_report,
            review_candidate=args.review_candidate,
        )
        if mode == "HOSTILE_SELF_TEST":
            mutants = run_hostile_self_test(args.source)
            print(f"selector closure checker self-test: PASS killed_mutants={mutants}")
            return 0
        if mode == "INVENTORY_GAP_REPORT":
            envelope, expanded = load_compact_source(args.source)
            report = build_inventory_gap_report(expanded)
            report_bytes = canonical_bytes(report) + b"\n"
            require(
                len(report_bytes) <= MAX_PROBE_OUTPUT_BYTES,
                (f"inventory-gap report exceeds {MAX_PROBE_OUTPUT_BYTES} bytes"),
            )
            _require_compact_source_unchanged(args.source, envelope)
            sys.stdout.buffer.write(report_bytes)
            return 0
        if mode == "PROBES_ONLY":
            envelope, expanded = load_compact_source(args.source)
            probes = run_bound_probes(expanded)
            _require_compact_source_unchanged(args.source, envelope)
            print(f"selector closure probe binding check: PASS probes={probes}")
            return 0
        envelope, expanded = load_compact_source(args.source)
        if mode == "EXACT_REVIEW_CANDIDATE_SEMANTICS_AND_PROBES":
            summary = validate_expanded_source(
                expanded,
                require_complete_allocation=True,
                allow_incomplete_allocation=True,
            )
            _require_review_candidate_boundary(expanded)
            probes = run_bound_probes(expanded)
            require_exact(
                validate_expanded_source(
                    expanded,
                    require_complete_allocation=True,
                    allow_incomplete_allocation=True,
                ),
                summary,
                "review-candidate semantics changed during probe execution",
            )
            _require_review_candidate_boundary(expanded)
        else:
            summary = validate_expanded_source(expanded)
            probes = (
                run_bound_probes(expanded)
                if mode == "STRICT_COMPLETE_SEMANTICS_AND_PROBES"
                else 0
            )
            if probes:
                require_exact(
                    validate_expanded_source(expanded),
                    summary,
                    "strict semantics changed during probe execution",
                )
        _require_compact_source_unchanged(args.source, envelope)
    except (
        ClosureCheckError,
        KeyError,
        OSError,
        SelectorClosureCodecError,
        TypeError,
    ) as error:
        print(f"selector closure check: FAIL: {error}", file=sys.stderr)
        return 1

    result_prefix = (
        "selector closure review candidate: LOCAL NON-GATING PASS "
        "allocation_status=INCOMPLETE_FAIL_CLOSED "
        "provenance_status=NOT_REVIEWED b01_complete=false "
        "release_authorized=false "
        if mode == "EXACT_REVIEW_CANDIDATE_SEMANTICS_AND_PROBES"
        else "selector closure check: PASS "
    )
    print(
        result_prefix + f"selectors={summary.selectors} "
        f"domains={summary.state_domains} "
        f"events={summary.events} "
        f"cases={summary.semantic_cases} "
        f"partition_branches={summary.partition_branches} "
        f"sidecars={summary.sidecars} "
        f"artifacts={summary.artifacts} "
        f"joint_transactions={summary.joint_transactions} "
        f"probes={probes} "
        f"expanded_sha256={summary.expanded_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
