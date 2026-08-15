#!/usr/bin/env python3
"""Fail-closed verifier for one B01 preliminary architecture-evidence result."""

# The bounded support import must install its exact snapshot before probe imports.
# ruff: noqa: I001

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from bounded_json_support import (
    BoundedJsonError,
    JsonLimits,
    parse_json_bytes,
)
import adr_example_semantics
import decision_probe
import freshness_acceptance_probe
import observer_authorization_probe
import observer_capture_probe
import source_issuance_index_probe
from source_inventory import (
    B01_SUPPORT_RELATIVE_PATHS,
    EXPECTED_B01_SOURCE_COUNT,
    SourceInventoryError,
    build_b01_source_inventory,
    read_bounded_relative_file,
)

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PREFIX = "NCP_B01_PRELIMINARY_RESULT="
ADR_EXAMPLE_SEMANTICS_PREFIX = "NCP_B01_ADR_EXAMPLE_SEMANTICS_RESULT="
MAX_RESULT_BYTES = 2_000_000
MAX_ADR_EXAMPLE_SEMANTICS_RESULT_BYTES = 262_144
EXPECTED_CONTRACT_SHA256 = (
    "9cae331742d01e9b164e029aa06c644e6b1886176d0816a6ef883af138355c90"
)
EXPECTED_FABLE_SHA256 = (
    "080ad93775d6dec018a08efeadd49b0d57e6162a90f4bc7cf9a8b43199246d32"
)
MAX_CONTRACT_MANIFEST_BYTES = 65_536
MAX_RESULT_AGE = timedelta(hours=1)
MAX_RESULT_FUTURE_SKEW = timedelta(minutes=5)
EXPECTED_DECISION_COUNTS = {
    "probes": 4,
    "finite_cases_evaluated": 159_993,
    "logic_mutants_killed": 24,
    "semantic_contrasts_reached": 22,
    "hostile_inputs_rejected": 616,
    "invariant_witnesses_reached": 119,
    "fault_cases_survived": 0,
}
EXPECTED_OBSERVER_AUTHORIZATION_COUNTS = {
    "server_transitions": 3,
    "boundary_transitions": 10,
    "boundaries": 2,
    "released_items": 1,
    "sealed_capability_issuances": 1,
    "authorized_read_decisions": 1,
    "exact_read_admission_retries": 1,
    "hostile_rejections": 169,
    "release_linearization_witnesses": 16,
    "registered_staged_artifact_types": 71,
    "closed_read_route_classes": 5,
}
RESULT_JSON_LIMITS = JsonLimits(
    maximum_bytes=MAX_RESULT_BYTES,
    maximum_depth=64,
    maximum_items=200_000,
    maximum_object_members=8_192,
    maximum_array_items=100_000,
    maximum_key_utf8_bytes=512,
    maximum_string_utf8_bytes=262_144,
    maximum_total_string_utf8_bytes=MAX_RESULT_BYTES,
    maximum_integer_chars=32,
    maximum_float_chars=64,
    allow_floats=True,
)
ADR_EXAMPLE_SEMANTICS_JSON_LIMITS = JsonLimits(
    maximum_bytes=MAX_ADR_EXAMPLE_SEMANTICS_RESULT_BYTES,
    maximum_depth=32,
    maximum_items=16_384,
    maximum_object_members=1_024,
    maximum_array_items=256,
    maximum_key_utf8_bytes=256,
    maximum_string_utf8_bytes=131_072,
    maximum_total_string_utf8_bytes=MAX_ADR_EXAMPLE_SEMANTICS_RESULT_BYTES,
    maximum_integer_chars=32,
    maximum_float_chars=64,
    allow_floats=False,
)
SMALL_RUNTIME_JSON_LIMITS = JsonLimits(
    maximum_bytes=65_536,
    maximum_depth=32,
    maximum_items=8_192,
    maximum_object_members=1_024,
    maximum_array_items=4_096,
    maximum_key_utf8_bytes=256,
    maximum_string_utf8_bytes=32_768,
    maximum_total_string_utf8_bytes=65_536,
    maximum_integer_chars=32,
    maximum_float_chars=64,
    allow_floats=True,
)
CONTRACT_MANIFEST_JSON_LIMITS = JsonLimits(
    maximum_bytes=MAX_CONTRACT_MANIFEST_BYTES,
    maximum_depth=24,
    maximum_items=4_096,
    maximum_object_members=256,
    maximum_array_items=2_048,
    maximum_key_utf8_bytes=256,
    maximum_string_utf8_bytes=16_384,
    maximum_total_string_utf8_bytes=MAX_CONTRACT_MANIFEST_BYTES,
    maximum_integer_chars=32,
    maximum_float_chars=64,
    allow_floats=False,
)
MODEL_CLAIM_BOUNDARY = (
    "No counterexample was found only within this finite abstraction. "
    "This is not TLA+, refinement, implementation proof, independent review, "
    "interoperability, plant safety evidence, or release authorization."
)
SMT_CLAIM_BOUNDARY = (
    "These finite formulas and satisfiable premises only challenge their "
    "encoded abstractions. They do not establish protocol correctness, code "
    "refinement, cryptographic security, plant safety, or release readiness."
)
ED25519_CLAIM_BOUNDARY = (
    "Thread and process CPU p95 values are machine-local computational tripwires "
    "over fixed messages and synchronous real Ed25519 verification calls. Maximum "
    "CPU and wall elapsed times are observations only. The process clock is retained "
    "to expose CPU used outside the calling thread. These measurements are not a "
    "production deadline, constant-time analysis, key-custody evidence, performance "
    "qualification, package-provenance result, or guarantee."
)
RESOURCE_CLAIM_BOUNDARY = (
    "These probes exercise explicit prototype bounds and one local machine. "
    "They do not select normative capacities, prove production deadlines, "
    "qualify performance, establish durability, certify safety, or close any "
    "external release gate."
)
SOURCE_ISSUANCE_INDEX_CLAIM_BOUNDARY = (
    "This deterministic finite source-index probe challenges only its local "
    "synthetic abstraction. It is not a protocol or implementation proof, "
    "interoperability result, transport-security qualification, plant-safety "
    "evidence, independent review, certification, or release authorization."
)
UTC_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{6})?Z$"
)


class ResultError(RuntimeError):
    """One malformed, stale, optimistic, incomplete, or unbounded result."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ResultError("value is not canonical bounded JSON data") from error


def _strongest_local_statement(case_count: int, mutation_count: int) -> str:
    return (
        "No counterexample was found within the recorded finite models, decision, "
        "observer-authorization, observer-capture, freshness-and-acceptance, "
        "source-issuance-index, fixed local resource, and ADR-example semantic "
        "probes. The separate Rust and TypeScript profile engines agreed on "
        f"{case_count} content-bound semantic cases and rejected {mutation_count} "
        "registered bounded mutations. Every other registered executable mutant "
        "was detected, every registered hostile input was rejected, and every "
        "registered invariant and semantic-contrast witness was reached within "
        "those encoded finite cases."
    )


def _outer_runtime_identity() -> dict[str, Any]:
    executable = Path(sys.executable).resolve(strict=True)
    content = executable.read_bytes()
    soabi = sysconfig.get_config_var("SOABI")
    if not isinstance(soabi, str) or not soabi:
        raise ResultError("outer Python SOABI is unavailable")
    return {
        "implementation": platform.python_implementation(),
        "version": platform.python_version(),
        "build": sys.version,
        "cache_tag": sys.implementation.cache_tag,
        "soabi": soabi,
        "isolated": sys.flags.isolated == 1,
        "no_user_site": sys.flags.no_user_site == 1,
        "safe_path": bool(sys.flags.safe_path),
        "executable": {
            "filename": executable.name,
            "sha256": _sha256(content),
            "bytes": len(content),
        },
    }


def _git(*arguments: str) -> str:
    git = shutil.which("git")
    if git is None:
        raise ResultError("git is unavailable")
    completed = subprocess.run(  # noqa: S603
        [git, *arguments],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.stderr:
        raise ResultError(f"git {' '.join(arguments)} emitted stderr")
    return completed.stdout.strip()


def _external_uv_environment() -> Path:
    raw = os.environ.get("UV_PROJECT_ENVIRONMENT")
    if not raw:
        raise ResultError("UV_PROJECT_ENVIRONMENT is required")
    path = Path(raw)
    if not path.is_absolute():
        raise ResultError("UV_PROJECT_ENVIRONMENT is not absolute")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ResultError("UV_PROJECT_ENVIRONMENT is unavailable") from error
    repository = REPOSITORY.resolve(strict=True)
    if (
        not resolved.is_dir()
        or resolved == repository
        or repository in resolved.parents
    ):
        raise ResultError(
            "UV_PROJECT_ENVIRONMENT is not an external environment directory"
        )
    return resolved


def _current_crypto_environment() -> dict[str, Any]:
    _external_uv_environment()
    uv = shutil.which("uv")
    if uv is None:
        raise ResultError("uv is unavailable")
    project = REPOSITORY / "prototypes/authenticated-ingress/signed-forwarding-envelope"
    completed = subprocess.run(  # noqa: S603
        [
            uv,
            "run",
            "--no-sync",
            "--offline",
            "--locked",
            "--project",
            str(project),
            "python",
            "-I",
            str(ROOT / "crypto_probe.py"),
            "--runtime-identity",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if (
        completed.returncode != 0
        or completed.stderr
        or len(completed.stdout.encode("utf-8")) > 65_536
    ):
        raise ResultError("Ed25519 runtime identity query failed")
    try:
        value = parse_json_bytes(
            completed.stdout.encode("utf-8"),
            limits=SMALL_RUNTIME_JSON_LIMITS,
            label="Ed25519 runtime identity",
        )
    except BoundedJsonError as error:
        raise ResultError(
            f"Ed25519 runtime identity is invalid JSON: {error}"
        ) from error
    if type(value) is not dict:
        raise ResultError("Ed25519 runtime identity query is not an object")
    _exact_keys(
        value,
        {"clock_metadata", "runtime_identity"},
        "queried Ed25519 runtime identity",
    )
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ResultError(f"{label} members differ from the checked shape")


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ResultError(f"{label} is not a positive integer")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ResultError(f"{label} is not a nonnegative integer")
    return value


def _verify_timestamp(value: Any) -> None:
    if not isinstance(value, str) or UTC_TIMESTAMP.fullmatch(value) is None:
        raise ResultError("generated timestamp is not canonical UTC")
    try:
        timestamp = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ResultError("generated timestamp is not RFC 3339") from error
    if timestamp.tzinfo != UTC:
        raise ResultError("generated timestamp is not UTC")
    now = datetime.now(UTC)
    if timestamp < now - MAX_RESULT_AGE:
        raise ResultError("generated timestamp is stale")
    if timestamp > now + MAX_RESULT_FUTURE_SKEW:
        raise ResultError("generated timestamp is implausibly in the future")


def _current_contract_manifest_sha256() -> str:
    try:
        content = read_bounded_relative_file(
            REPOSITORY,
            "contract/manifest.v1.json",
            maximum_bytes=MAX_CONTRACT_MANIFEST_BYTES,
            label="contract manifest",
        )
    except (OSError, SourceInventoryError) as error:
        raise ResultError(f"contract manifest snapshot failed: {error}") from error
    try:
        value = parse_json_bytes(
            content,
            limits=CONTRACT_MANIFEST_JSON_LIMITS,
            label="contract manifest",
        )
    except BoundedJsonError as error:
        raise ResultError(f"contract manifest JSON is invalid: {error}") from error
    if (
        type(value) is not dict
        or value.get("contract_digest_sha256") != EXPECTED_CONTRACT_SHA256
    ):
        raise ResultError("current contract manifest identity changed")
    return _sha256(content)


def _current_z3_binary_sha256() -> str:
    z3 = shutil.which("z3")
    if z3 is None:
        raise ResultError("z3 is unavailable")
    return _sha256(Path(z3).resolve().read_bytes())


def _load() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_RESULT_BYTES + 1)
    if len(raw) > MAX_RESULT_BYTES:
        raise ResultError("result exceeds the verifier input bound")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ResultError("result is not strict UTF-8") from error
    if "\r" in text:
        raise ResultError("result contains a carriage return")
    if text.endswith("\n"):
        text = text[:-1]
    if not text or "\n" in text or not text.startswith(PREFIX):
        raise ResultError("expected exactly one prefixed result line")
    try:
        value = parse_json_bytes(
            text[len(PREFIX) :].encode("utf-8"),
            limits=RESULT_JSON_LIMITS,
            label="preliminary evidence result",
        )
    except BoundedJsonError as error:
        raise ResultError(f"result is not bounded strict JSON: {error}") from error
    if type(value) is not dict:
        raise ResultError("result root is not an object")
    return value


def _load_adr_example_semantics() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_ADR_EXAMPLE_SEMANTICS_RESULT_BYTES + 1)
    if len(raw) > MAX_ADR_EXAMPLE_SEMANTICS_RESULT_BYTES:
        raise ResultError(
            "ADR-example semantic result exceeds the verifier input bound"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ResultError("ADR-example semantic result is not strict UTF-8") from error
    if "\r" in text:
        raise ResultError("ADR-example semantic result contains a carriage return")
    if text.endswith("\n"):
        text = text[:-1]
    if not text or "\n" in text or not text.startswith(ADR_EXAMPLE_SEMANTICS_PREFIX):
        raise ResultError(
            "expected exactly one prefixed ADR-example semantic result line"
        )
    try:
        value = parse_json_bytes(
            text[len(ADR_EXAMPLE_SEMANTICS_PREFIX) :].encode("utf-8"),
            limits=ADR_EXAMPLE_SEMANTICS_JSON_LIMITS,
            label="ADR-example semantic result",
        )
    except BoundedJsonError as error:
        raise ResultError(
            f"ADR-example semantic result is not bounded strict JSON: {error}"
        ) from error
    if type(value) is not dict:
        raise ResultError("ADR-example semantic result root is not an object")
    return value


def _load_standalone_probe(*, label: str) -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_RESULT_BYTES + 1)
    if len(raw) > MAX_RESULT_BYTES:
        raise ResultError(f"{label} result exceeds the verifier input bound")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ResultError(f"{label} result is not strict UTF-8") from error
    if "\r" in text:
        raise ResultError(f"{label} result contains a carriage return")
    if text.endswith("\n"):
        text = text[:-1]
    if not text or "\n" in text:
        raise ResultError(f"expected exactly one {label} result line")
    try:
        value = parse_json_bytes(
            text.encode("utf-8"),
            limits=RESULT_JSON_LIMITS,
            label=f"{label} result",
        )
    except BoundedJsonError as error:
        raise ResultError(
            f"{label} result is not bounded strict JSON: {error}"
        ) from error
    if type(value) is not dict:
        raise ResultError(f"{label} result root is not an object")
    return value


def _load_decision_probe() -> dict[str, Any]:
    return _load_standalone_probe(label="decision-probe")


def _load_observer_authorization_probe() -> dict[str, Any]:
    return _load_standalone_probe(label="observer-authorization-probe")


def _verify_sources(value: dict[str, Any]) -> None:
    sources = value["sources"]
    if type(sources) is not list or len(sources) != EXPECTED_B01_SOURCE_COUNT:
        raise ResultError("source inventory does not have the exact source count")
    paths: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise ResultError(f"sources[{index}] is not an object")
        _exact_keys(source, {"path", "bytes", "sha256"}, f"sources[{index}]")
        path = source["path"]
        if (
            not isinstance(path, str)
            or (
                not path.startswith("prototypes/b01-architecture-evidence/")
                and path not in B01_SUPPORT_RELATIVE_PATHS
            )
            or path in paths
            or not isinstance(source["bytes"], int)
            or isinstance(source["bytes"], bool)
            or source["bytes"] <= 0
            or not isinstance(source["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", source["sha256"]) is None
        ):
            raise ResultError(f"sources[{index}] identity is invalid or duplicate")
        paths.add(path)
    try:
        expected_sources = build_b01_source_inventory(ROOT, REPOSITORY)
    except (OSError, SourceInventoryError) as error:
        raise ResultError(f"source inventory failed closed: {error}") from error
    if sources != expected_sources:
        raise ResultError(
            "source inventory does not equal the bounded checked source set"
        )


def _verify_exploration(
    value: Any,
    *,
    label: str,
    expected_actions: set[str],
    expected_witnesses: set[str],
    minimum_states: int,
) -> None:
    if not isinstance(value, dict):
        raise ResultError(f"{label} is not an object")
    _exact_keys(
        value,
        {
            "states",
            "transitions",
            "maximum_depth",
            "action_counts",
            "witnesses",
        },
        label,
    )
    if _positive_int(value["states"], f"{label}.states") < minimum_states:
        raise ResultError(f"{label} exploration is unexpectedly small")
    _positive_int(value["transitions"], f"{label}.transitions")
    _positive_int(value["maximum_depth"], f"{label}.maximum_depth")
    action_counts = value["action_counts"]
    if not isinstance(action_counts, dict) or set(action_counts) != expected_actions:
        raise ResultError(f"{label} action coverage differs from the checked set")
    for action, count in action_counts.items():
        _positive_int(count, f"{label}.action_counts.{action}")
    witnesses = value["witnesses"]
    if (
        not isinstance(witnesses, list)
        or witnesses != sorted(expected_witnesses)
        or any(not isinstance(item, str) for item in witnesses)
    ):
        raise ResultError(f"{label} witnesses differ from the checked set")


def _verify_model(value: Any) -> None:
    if not isinstance(value, dict):
        raise ResultError("model result is not an object")
    _exact_keys(
        value,
        {
            "schema",
            "scope",
            "claim_boundary",
            "composition",
            "deny_lifecycle",
            "migration_cutover",
            "mutation_kill_matrix",
            "counts",
        },
        "model",
    )
    if (
        value["schema"] != "ncp.b01-preliminary-model-result.v2"
        or value["scope"] != "bounded-pre-ratification-counterexample-discovery"
        or value["claim_boundary"] != MODEL_CLAIM_BOUNDARY
    ):
        raise ResultError("bounded model identity or claim boundary drifted")
    _verify_exploration(
        value["composition"],
        label="model.composition",
        expected_actions={
            "begin_handover",
            "deliver",
            "expire_lease",
            "finish_handover",
            "inject_simulation",
            "inject_wrong_epoch",
            "inject_wrong_generation",
            "inject_wrong_holder",
            "inject_wrong_term",
            "issue_direct",
            "issue_haldir",
            "persist_handover_term",
            "quiesce_handover",
            "recover_body",
            "restart_body",
            "restart_stream",
            "resume_transfer",
            "retire_handover",
        },
        expected_witnesses={
            "delayed_stale_rejected_while_fresh_command_pending",
            "clean_restart_recovered_current_holder",
            "completed_transfer_restart_recovered_current_holder",
            "direct_to_gated_handover_completed",
            "fresh_command_applied",
            "hostile_or_stale_command_rejected",
            "restart_or_expiry_recovered",
            "restart_preserved_quiesced_transfer",
            "restart_preserved_requested_transfer",
            "restart_preserved_retired_transfer",
            "restart_preserved_term_persisted_transfer",
            "restart_resumed_quiesced_transfer",
            "restart_resumed_requested_transfer",
            "restart_resumed_retired_transfer",
            "restart_resumed_term_persisted_transfer",
            "simulation_command_rejected",
            "two_commands_in_flight",
            "wrong_epoch_rejected",
            "wrong_generation_rejected",
            "wrong_holder_rejected",
            "wrong_term_rejected",
        },
        minimum_states=1_000,
    )
    _verify_exploration(
        value["deny_lifecycle"],
        label="model.deny_lifecycle",
        expected_actions={
            "abstained_evidence_attempt",
            "apply_profile_admitted_deny",
            "assessor_profile_attempt",
            "assessor_allow_attempt",
            "authenticated_base_widen",
            "authenticated_widen",
            "base_policy_deny",
            "complete_recovery_dwell",
            "disable",
            "early_authenticated_recovery_attempt",
            "expire",
            "ineligible_verdict_attempt",
            "install_qualified_haldir_profile",
            "missing_qualification_attempt",
            "producer_requested_deny",
            "record_only",
            "restart",
            "retract",
            "same_causal_revision_attempt",
            "unauthenticated_base_widen",
            "unauthenticated_clear",
            "unauthenticated_deny_attempt",
        },
        expected_witnesses={
            "abstained_evidence_attempt_blocked",
            "assessor_profile_attempt_blocked",
            "authenticated_base_widen_succeeded",
            "authenticated_deny_removal_succeeded",
            "disable_remains_non_widening",
            "early_recovery_blocked",
            "expire_remains_non_widening",
            "independent_qualified_profile_installed",
            "ineligible_verdict_attempt_blocked",
            "missing_qualification_attempt_blocked",
            "producer_requested_deny_blocked",
            "profile_admitted_deny_applied",
            "record_only_is_identity",
            "recovery_dwell_completed",
            "restart_preserved_applied_deny",
            "retract_remains_non_widening",
            "same_causal_revision_attempt_blocked",
            "unauthenticated_deny_attempt_blocked",
            "unauthenticated_widen_blocked",
        },
        minimum_states=20,
    )
    _verify_exploration(
        value["migration_cutover"],
        label="model.migration_cutover",
        expected_actions={
            "activate_v08_rollback",
            "activate_v10",
            "begin_cutover",
            "begin_rollback",
            "deliver",
            "issue_v08_pre_cutover",
            "issue_v08_rollback",
            "issue_v10",
            "quiesce_cutover",
            "quiesce_rollback",
        },
        expected_witnesses={
            "cutover_quiescence_reached",
            "fresh_rollback_v08_command_applied",
            "fresh_v08_rollback_incarnation_activated",
            "fresh_v10_command_applied",
            "fresh_v10_incarnation_activated",
            "pre_cutover_v08_rejected_after_rollback",
            "pre_cutover_v08_rejected_in_v10",
            "rollback_quiescence_reached",
        },
        minimum_states=1_000,
    )
    counts = value["counts"]
    if counts != {
        "models": 3,
        "mutations_killed": 38,
        "mutations_survived": 0,
    }:
        raise ResultError("bounded model mutation matrix is incomplete")
    expected_mutations = {
        ("composition", "omit_generation"),
        ("composition", "ordered_generation"),
        ("composition", "omit_term"),
        ("composition", "omit_epoch"),
        ("composition", "omit_holder"),
        ("composition", "simulation_as_plant"),
        ("composition", "wrong_haldir_principal"),
        ("composition", "overlap_handover"),
        ("composition", "restart_loses_requested_latch"),
        ("composition", "restart_loses_quiesced_latch"),
        ("composition", "restart_loses_retired_latch"),
        ("composition", "restart_loses_term_persisted_latch"),
        ("composition", "complete_from_requested"),
        ("composition", "complete_from_quiesced"),
        ("composition", "complete_from_retired"),
        ("composition", "complete_to_old_holder"),
        ("deny_lifecycle", "expiry_clears"),
        ("deny_lifecycle", "retraction_clears"),
        ("deny_lifecycle", "disable_clears"),
        ("deny_lifecycle", "restart_drops"),
        ("deny_lifecycle", "unauthenticated_clear"),
        ("deny_lifecycle", "record_only_clears"),
        ("deny_lifecycle", "assessor_allows"),
        ("deny_lifecycle", "unauthenticated_deny_applies"),
        ("deny_lifecycle", "producer_request_applies"),
        ("deny_lifecycle", "assessor_profile_applies"),
        ("deny_lifecycle", "missing_qualification_applies"),
        ("deny_lifecycle", "ineligible_verdict_applies"),
        ("deny_lifecycle", "abstention_applies"),
        ("deny_lifecycle", "same_causal_revision_applies"),
        ("deny_lifecycle", "recovery_dwell_bypass"),
        ("deny_lifecycle", "authenticated_widen_disabled"),
        ("migration_cutover", "dual_stack_cutover"),
        ("migration_cutover", "activate_v10_before_quiescence"),
        ("migration_cutover", "activate_v08_before_quiescence"),
        ("migration_cutover", "rollback_reuses_v08_incarnation"),
        ("migration_cutover", "ordered_v08_incarnation"),
        ("migration_cutover", "accept_v08_in_v10"),
    }
    mutations = value["mutation_kill_matrix"]
    if not isinstance(mutations, list) or len(mutations) != len(expected_mutations):
        raise ResultError("bounded model mutation entries are incomplete")
    observed: set[tuple[str, str]] = set()
    for index, mutation in enumerate(mutations):
        if not isinstance(mutation, dict):
            raise ResultError(f"model mutation {index} is not an object")
        _exact_keys(
            mutation,
            {"model", "mutation", "detected", "reason", "trace"},
            f"model.mutation_kill_matrix[{index}]",
        )
        identity = (mutation["model"], mutation["mutation"])
        if (
            identity in observed
            or mutation["detected"] is not True
            or not isinstance(mutation["reason"], str)
            or not mutation["reason"]
            or not isinstance(mutation["trace"], list)
            or any(not isinstance(item, str) for item in mutation["trace"])
        ):
            raise ResultError(f"model mutation {index} is malformed or duplicate")
        observed.add(identity)
    if observed != expected_mutations:
        raise ResultError("bounded model mutation identities differ")


@lru_cache(maxsize=1)
def _expected_adr_example_semantics_result() -> dict[str, Any]:
    try:
        result = adr_example_semantics.build_result(self_test=True)
    except (
        adr_example_semantics.CoordinatorError,
        MemoryError,
        OSError,
        UnicodeError,
    ) as error:
        raise ResultError(
            f"ADR-example semantic result recomputation failed: {error}"
        ) from error
    if type(result) is not dict:
        raise ResultError("recomputed ADR-example semantic result is not an object")
    return result


def _verify_adr_example_semantics(value: Any) -> None:
    if type(value) is not dict:
        raise ResultError("ADR-example semantic result is not an exact object")
    expected = _expected_adr_example_semantics_result()
    _exact_keys(value, set(expected), "adr_example_semantics")
    if _canonical_json(value) != _canonical_json(expected):
        raise ResultError(
            "ADR-example semantic result failed exact canonical recomputation"
        )
    if (
        value.get("schema") != "ncp.b01-adr-example-semantics-coordinator-result.v1"
        or value.get("task") != "B01"
        or value.get("candidate") != "1.0.0-rc.1"
        or value.get("wire_version") != "1.0"
        or value.get("engines") != ["rust", "typescript"]
        or value.get("case_count") != 25
        or not isinstance(value.get("mutation_count"), int)
        or isinstance(value.get("mutation_count"), bool)
        or value["mutation_count"] <= 0
        or value.get("exact_semantic_match") is not True
        or value.get("exact_source_identity_match") is not True
        or value.get("source_tree_build_output_absent") is not True
    ):
        raise ResultError("ADR-example semantic identity or coverage drifted")
    for field in ("corpus_sha256", "semantic_parity_sha256"):
        field_value = value.get(field)
        if (
            not isinstance(field_value, str)
            or re.fullmatch(r"[0-9a-f]{64}", field_value) is None
        ):
            raise ResultError(f"ADR-example semantic {field} is not a SHA-256")
    self_tests = value.get("coordinator_self_tests")
    if type(self_tests) is not dict:
        raise ResultError("ADR-example semantic self-test result is not an object")
    _exact_keys(self_tests, {"detected", "executed"}, "semantic coordinator tests")
    executed = _positive_int(self_tests.get("executed"), "semantic tests executed")
    detected = _positive_int(self_tests.get("detected"), "semantic tests detected")
    if executed != 29 or detected != 29:
        raise ResultError("ADR-example semantic self-tests are incomplete")
    claims = value.get("claim_boundary")
    expected_claims = {
        "adrs_accepted",
        "external_gate_satisfied",
        "independent_evidence_satisfied",
        "interoperability_established",
        "normative_contract_changed",
        "production_admission_implemented",
        "release_authorized",
    }
    if type(claims) is not dict:
        raise ResultError("ADR-example semantic claim boundary is not an object")
    _exact_keys(claims, expected_claims, "ADR-example semantic claim boundary")
    if any(claims.get(field) is not False for field in expected_claims):
        raise ResultError("ADR-example semantic claim boundary is optimistic")
    sources = value.get("engine_source_identities")
    if type(sources) is not dict:
        raise ResultError("ADR-example engine source identities are not an object")
    _exact_keys(sources, {"rust", "typescript"}, "semantic engine source identities")
    for engine in ("rust", "typescript"):
        identities = sources.get(engine)
        if not isinstance(identities, list) or not identities:
            raise ResultError(f"{engine} semantic source identities are incomplete")
        paths: list[str] = []
        for index, identity in enumerate(identities):
            if type(identity) is not dict:
                raise ResultError(f"{engine} semantic source {index} is not an object")
            _exact_keys(
                identity,
                {"byte_length", "path", "sha256"},
                f"{engine} semantic source {index}",
            )
            path = identity.get("path")
            digest = identity.get("sha256")
            if (
                not isinstance(path, str)
                or not path
                or path in paths
                or not isinstance(digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            ):
                raise ResultError(f"{engine} semantic source {index} is malformed")
            _positive_int(
                identity.get("byte_length"),
                f"{engine} semantic source {index} byte length",
            )
            paths.append(path)
        if paths != sorted(paths):
            raise ResultError(f"{engine} semantic source paths are not sorted")


@lru_cache(maxsize=1)
def _expected_decision_probe_result() -> str:
    return json.dumps(
        decision_probe.build_result(),
        separators=(",", ":"),
        sort_keys=True,
    )


def _verify_decision_probe(value: Any) -> None:
    if (
        not isinstance(value, dict)
        or json.dumps(
            value,
            separators=(",", ":"),
            sort_keys=True,
        )
        != _expected_decision_probe_result()
    ):
        raise ResultError("decision probe failed deterministic semantic replay")
    sections = tuple(
        value.get(name)
        for name in (
            "observer_projection",
            "grant_lifecycle",
            "capture_action",
            "surface_inventory",
        )
    )
    if not all(isinstance(section, dict) for section in sections):
        raise ResultError("decision probe sections are incomplete")
    observer, lifecycle, capture, surfaces = sections
    derived_counts = {
        "probes": len(sections),
        "finite_cases_evaluated": (
            observer["case_count"]
            + lifecycle["case_count"]
            + capture["targeted_action_case_count"]
        ),
        "logic_mutants_killed": (
            len(observer["logic_mutants"]) + len(surfaces["logic_mutants"])
        ),
        "semantic_contrasts_reached": (
            len(lifecycle["semantic_contrasts"]) + len(capture["semantic_contrasts"])
        ),
        "hostile_inputs_rejected": sum(
            len(section.get("hostile_inputs", ())) for section in sections
        ),
        "invariant_witnesses_reached": sum(
            len(section["invariant_witnesses"]) for section in sections
        ),
        "fault_cases_survived": 0,
    }
    counts = value.get("counts")
    if (
        not isinstance(counts, dict)
        or counts != derived_counts
        or counts != EXPECTED_DECISION_COUNTS
    ):
        raise ResultError("decision probe coverage counts drifted")


@lru_cache(maxsize=1)
def _expected_observer_authorization_result() -> str:
    return json.dumps(
        observer_authorization_probe.build_result(),
        separators=(",", ":"),
        sort_keys=True,
    )


def _verify_observer_authorization_probe(value: Any) -> None:
    if not isinstance(value, dict):
        raise ResultError("observer authorization result is not an object")
    if json.dumps(value, separators=(",", ":"), sort_keys=True) != (
        _expected_observer_authorization_result()
    ):
        raise ResultError(
            "observer authorization probe failed deterministic semantic replay"
        )
    if value.get("counts") != EXPECTED_OBSERVER_AUTHORIZATION_COUNTS:
        raise ResultError("observer authorization coverage counts drifted")
    claim_boundary = value.get("claim_boundary")
    if (
        not isinstance(claim_boundary, dict)
        or claim_boundary.get("status") != "synthetic_pre_ratification_non_normative"
        or claim_boundary.get("wire_implementation") is not False
        or claim_boundary.get("interoperability") != "NOT RUN"
        or claim_boundary.get("release_readiness") != "NOT RUN"
        or claim_boundary.get("live_transport_principal_binding") != "NOT RUN"
        or claim_boundary.get("capability_issuer_cryptographic_qualification")
        != "NOT RUN"
        or claim_boundary.get("external_revocation_propagation") != "NOT RUN"
        or claim_boundary.get("external_transport_enqueue_evidence")
        != "synthetic_in_process_coordinator_record_only"
        or claim_boundary.get("external_transport_enqueue_durability") != "NOT RUN"
        or claim_boundary.get("capability_seal_evidence")
        != "synthetic_hmac_fixture_only"
        or claim_boundary.get("read_decision_seal_evidence")
        != "synthetic_hmac_fixture_only"
        or claim_boundary.get("read_decision_authority_effect")
        != "PREFLIGHT_ONLY_RELEASE_RECHECK_REQUIRED"
    ):
        raise ResultError("observer authorization claim boundary drifted")


@lru_cache(maxsize=1)
def _expected_observer_capture_result() -> str:
    return json.dumps(
        observer_capture_probe.build_result(),
        separators=(",", ":"),
        sort_keys=True,
    )


def _verify_observer_capture_probe(value: Any) -> None:
    if not isinstance(value, dict):
        raise ResultError("observer capture result is not an object")
    if value.get("schema") != "ncp.b01-observer-capture-probe-result.v7":
        raise ResultError("observer capture result schema drifted")
    if json.dumps(value, separators=(",", ":"), sort_keys=True) != (
        _expected_observer_capture_result()
    ):
        raise ResultError("observer capture probe failed deterministic semantic replay")
    if value.get("counts") != {
        "targeted_cases": 249,
        "targeted_case_components": {
            "grant_lifecycle_decision_cases": 186,
            "capture_action_decision_cases": 63,
        },
        "logic_mutants_executed": 10,
        "logic_mutants_killed": 10,
        "logic_mutants_survived": 0,
        "semantic_contrasts_reached": 22,
        "hostile_inputs_rejected": 444,
        "bridge_commitment_mutations_executed": 672,
        "bridge_commitment_mutations_rejected": 672,
        "invariant_witnesses_reached": 73,
    }:
        raise ResultError("observer capture coverage counts drifted")
    lifecycle = value.get("grant_lifecycle")
    if (
        not isinstance(lifecycle, dict)
        or lifecycle.get("case_count") != 186
        or lifecycle.get("admitted") != 36
        or lifecycle.get("rejected") != 150
        or lifecycle.get("hostile_input_count") != 150
    ):
        raise ResultError("observer capture lifecycle counts drifted")
    bridge = lifecycle.get("observer_read_capture_bridge")
    if (
        not isinstance(bridge, dict)
        or set(bridge)
        != {
            "additional_closed_route_classes",
            "admitted_before_cut_survives_later_security_state",
            "capsule_backed_current_axis_members",
            "capsule_backed_current_axis_slots",
            "current_delivery_route_classes",
            "decision_authority_effect",
            "decision_seal_evidence",
            "decision_type",
            "deterministic_extraction_receipt_count",
            "extraction_replay",
            "extraction_source",
            "future_read_authority_from_capsule",
            "historical_capsule_count",
            "membership_type",
            "release_chain_digest",
            "scope_type",
            "status",
        }
        or bridge["current_delivery_route_classes"]
        != [
            "ACTION_COMMAND_PROPOSAL",
            "OBSERVATION_FRAME",
            "PERCEPTION_PROJECTED_OBSERVATION",
            "PERCEPTION_SENSOR_FRAME",
        ]
        or bridge["additional_closed_route_classes"]
        != ["OBSERVATION_COMMAND_DISPOSITION"]
        or bridge["capsule_backed_current_axis_slots"] != ["A", "D", "L", "V"]
        or bridge["capsule_backed_current_axis_members"]
        != {
            "A": ["a0"],
            "D": ["d_left", "d_right"],
            "L": ["l0"],
            "V": ["v0"],
        }
        or bridge["historical_capsule_count"] != 7
        or bridge["deterministic_extraction_receipt_count"] != 7
        or bridge["extraction_source"] != "RETAINED_ADMITTED_PAYLOAD_BYTES"
        or bridge["extraction_replay"] != "REQUIRED_FOR_EACH_SEMANTIC_MEMBER_SAMPLE"
        or bridge["scope_type"] != "CanonicalObserverReadScope"
        or bridge["membership_type"] != "ObserverBoundaryReadScopeMembership"
        or bridge["decision_type"] != "SealedObserverReadAuthorizationDecision"
        or bridge["decision_authority_effect"]
        != "PREFLIGHT_ONLY_RELEASE_RECHECK_REQUIRED"
        or bridge["decision_seal_evidence"] != "synthetic_hmac_fixture_only"
        or bridge["future_read_authority_from_capsule"] is not False
        or bridge["admitted_before_cut_survives_later_security_state"] is not True
        or bridge["status"] != "SYNTHETIC_PRE_RATIFICATION_NON_NORMATIVE"
        or not isinstance(bridge["release_chain_digest"], str)
        or re.fullmatch(r"[0-9a-f]{64}", bridge["release_chain_digest"]) is None
    ):
        raise ResultError("observer read/capture bridge closure drifted")
    architecture = lifecycle.get("observer_attachment_architecture")
    expected_retirement_requirements = [
        "EXACT_INSTALLED_SOURCE_RETIREMENT_PREPARATION_RECEIPT",
        "EXACT_CURRENT_TARGET_HISTORY_SELECTOR_COMPARE",
        "COMPLETE_TARGET_PARTITION",
        "NO_LIVE_OR_ALLOCATED_SOURCE_GENERATION",
        "PUBLISHED_OR_SEALED_UNRESOLVED_BRANCH_PER_TARGET",
        "SOURCE_LOGICAL_SESSION_PERMANENTLY_RETIRED",
    ]
    if (
        not isinstance(architecture, dict)
        or architecture.get("status")
        != ("SYNTHETIC_PRE_RATIFICATION_NON_NORMATIVE_QUALIFIED_DOMAIN_MODEL")
        or architecture.get("valid_decision_cases") != 24
        or architecture.get("hostile_decision_cases") != 40
        or architecture.get("attach_allocates_adr001_generation") is not False
        or architecture.get("attach_registers_source_logical_session_lineage")
        is not False
        or architecture.get("source_lineage_registration_precondition")
        != "REGISTER_SOURCE_LOGICAL_SESSION_LINEAGE"
        or architecture.get("target_key_fields")
        != [
            "authenticated_requester_principal",
            "authority_realm_key",
            "source_logical_session_id",
            "source_session_kind",
        ]
        or not {
            "security_epoch",
            "security_state_digest",
            "source_generation",
        }.issubset(architecture.get("target_key_excluded_fields", []))
        or architecture.get("authority_transaction_domain_key_semantics")
        != "EXACT_OBSERVER_AUTHORITY_REALM_KEY"
        or architecture.get("target_history_scope")
        != "AUTHORITY_TRANSACTION_DOMAIN_GLOBAL_MANIFEST_BOUNDED"
        or architecture.get("capacity_sharding")
        != "RESERVED_SIMULATION_AND_PLANT_SHARDS_NO_CROSS_STARVATION"
        or architecture.get("source_retirement_branch_derivation")
        != "TERMINAL_CAS_FROM_CURRENT_TARGET_HISTORY_SELECTOR"
        or architecture.get("source_retirement_target_branches")
        != ["PUBLISHED", "SEALED_UNRESOLVED"]
        or architecture.get("publication_after_preparation")
        != "MAY_WIN_TARGET_SELECTOR_CAS_THEN_TERMINAL_RETRY"
        or architecture.get("publication_after_seal") != "REJECT"
        or architecture.get("stale_terminal_target_selector_compare")
        != "REJECT_WITHOUT_MUTATION"
        or architecture.get("terminal_namespace_registry_compare")
        != "CURRENT_SAME_SELECTOR_MONOTONIC_HEAD_AND_UNCHANGED_SOURCE_ENTRY"
        or architecture.get("namespace_rotation_after_preparation")
        != "ALLOW_WHEN_SOURCE_ENTRY_DIGEST_IS_UNCHANGED"
        or architecture.get("namespace_entry_change_after_preparation")
        != "REJECT_TERMINAL_WITHOUT_PARTIAL_MUTATION"
        or architecture.get("permanent_source_reclamation_requires")
        != expected_retirement_requirements
        or architecture.get("retirement_tombstone_future_receipt_dependency")
        != "STRUCTURALLY_ABSENT"
        or architecture.get("retained_terminal_lineage_phase")
        != "SOURCE_LOGICAL_SESSION_PERMANENTLY_RETIRED"
        or architecture.get("unresolved_quarantine_state") != "SEALED_UNRESOLVED"
        or architecture.get("quarantine_late_closure_effect")
        != "ARCHIVE_ENRICHMENT_ONLY_NO_AUTHORITY"
        or architecture.get("namespace_registry_selector_cardinality")
        != "EXACTLY_ONE_PER_AUTHORITY_TRANSACTION_DOMAIN"
        or architecture.get("namespace_registry_rotation")
        != "PRESERVE_COMPLETE_AUTHORITATIVE_ENTRY_PROJECTION"
        or architecture.get("retired_source_namespace_reuse") != "REJECT"
        or architecture.get("history_logic_mutants_executed") != 10
        or architecture.get("history_logic_mutants_killed") != 10
        or architecture.get("live_interoperability_qualified") is not False
    ):
        raise ResultError("observer attachment architecture scope drifted")
    capture = value.get("capture_action")
    expected_fail_safe_components = {
        "valid_action_cases": 3,
        "invalid_non_active_cases": 10,
        "invalid_active_cases": 5,
        "pre_context_cases": 7,
        "manifest_denied_cases": 3,
        "invalid_authority_cases": 4,
        "replay_and_identity_cases": 7,
        "crash_and_recovery_cases": 2,
        "unified_physical_dag_hostile_cases": 8,
        "actuation_domain_binding_hostile_cases": 4,
    }
    if (
        not isinstance(capture, dict)
        or capture.get("fail_safe_targeted_case_count") != 53
        or capture.get("fail_safe_targeted_case_components")
        != expected_fail_safe_components
        or capture.get("fail_safe_targeted_case_count")
        != sum(expected_fail_safe_components.values())
    ):
        raise ResultError("observer fail-safe case components drifted")
    if capture.get("unified_physical_boundary_scope") != {
        "observer_executable_paths": ["INITIAL_HOLD", "INITIAL_ESTOP"],
        "freshness_probe_paths": [
            "HOLD_TO_ESTOP_UPGRADE",
            "RETIREMENT_DRAIN_ESTOP",
            "PROFILE_CAPACITY_RETIREMENT_RESTRICTIVE",
        ],
        "all_paths_share_required_stage_order": True,
        "live_boundary_qualified": False,
        "physical_safety_established": False,
    }:
        raise ResultError("observer unified physical-boundary scope drifted")
    domain_key_digest = observer_capture_probe._actuation_authority_domain_key_digest()
    if capture.get("actuation_authority_domain_scope") != {
        "key_type": "ActuationAuthorityDomainKey",
        "key_body": observer_capture_probe._actuation_authority_domain_key_body(),
        "domain_key_digest": domain_key_digest,
        "domain_bindings_per_plant_generation": 1,
        "arbiter_mirror_cardinality": "SCALAR_EXACTLY_ONE",
        "mirror_set_permitted": False,
        "qualified_atomic_multi_actuator_boundary_permitted": True,
        "cross_domain_atomic_success_permitted": False,
        "independent_domain_session_rule": "DISTINCT_SESSIONS",
        "global_conflict_registry_probe": "freshness_acceptance_probe",
        "selector_scope_type": "PhysicalActuationJurisdictionKey",
        "physical_actuation_jurisdiction_key": (
            observer_capture_probe.PHYSICAL_ACTUATION_JURISDICTION_KEY
        ),
        "physical_actuation_jurisdiction_incarnation": (
            observer_capture_probe.PHYSICAL_ACTUATION_JURISDICTION_INCARNATION
        ),
        "jurisdiction_selector_cardinality": ("ONE_PER_JURISDICTION_INCARNATION"),
        "live_jurisdiction_incarnations_per_key": 1,
        "live_boundary_qualified": False,
    }:
        raise ResultError("observer actuation-authority domain scope drifted")
    qualification = (
        capture.get("selector_evidence_qualification")
        if isinstance(capture, dict)
        else None
    )
    qualification_sections = (
        tuple(
            qualification.get(name)
            for name in (
                "galadriel_lifecycle",
                "galadriel_handoff",
                "prisoma_numeric_executor",
                "haldir_policy",
                "haldir_commander",
            )
        )
        if isinstance(qualification, dict)
        else ()
    )
    if (
        not isinstance(qualification, dict)
        or len(qualification_sections) != 5
        or not all(isinstance(section, dict) for section in qualification_sections)
        or qualification.get("status") != "NOT_QUALIFIED_AS_SELECTOR_CLOSURE_EVIDENCE"
        or qualification_sections[0].get("status")
        != "STRUCTURAL_HEAD_COMMIT_CHAIN_ONLY"
        or qualification_sections[1].get("status")
        != "MISSING_PENDING_RECORD_INSTALL_H1"
        or qualification_sections[2].get("status")
        != "LEGACY_THREE_TRANSITION_SUCCESS_PATH_ONLY"
        or qualification_sections[2].get("input_exclusion_terminal_cas_count") != 0
        or qualification_sections[3].get("status")
        != "STRUCTURAL_SELECTED_PROFILE_PATH_NOT_QUALIFIED"
        or qualification_sections[3].get("direct_no_profile_terminal_count") != 0
        or qualification_sections[4].get("status")
        != "BOUNDED_SYNTHETIC_LOCAL_OUTBOX_PATH_ONLY"
        or qualification_sections[4].get("commander_feedback_transition_count") != 0
    ):
        raise ResultError("legacy selector-evidence qualification boundary drifted")
    publication_boundaries = (
        capture.get("haldir_publication_boundaries")
        if isinstance(capture, dict)
        else None
    )
    if publication_boundaries != {
        "local_atomic_result": "RELEASED_TO_LOCAL_DURABLE_NCP_OUTBOX",
        "local_result_requires_reconciliation": False,
        "transport_disposition_branch_shapes": [
            {
                "result": "ACCEPTED_BY_NCP_TRANSPORT",
                "acceptance_receipt_required": True,
                "definitive_no_acceptance_evidence_required": False,
                "reconciliation_required": False,
            },
            {
                "result": "REJECTED_BEFORE_NCP_TRANSPORT_ACCEPTANCE",
                "acceptance_receipt_required": False,
                "definitive_no_acceptance_evidence_required": True,
                "reconciliation_required": False,
            },
            {
                "result": "AMBIGUOUS_AFTER_NCP_TRANSPORT",
                "acceptance_receipt_required": False,
                "definitive_no_acceptance_evidence_required": False,
                "reconciliation_required": True,
            },
        ],
    }:
        raise ResultError("Haldir local-outbox/transport boundary drifted")
    association_branches = capture.get("restrictive_effect_association_branches")
    if not isinstance(association_branches, dict):
        raise ResultError("restrictive-effect association branches are absent")
    expected_association_shapes = {
        "HOLD": {
            "disposition_path": ["received", "admitted", "hold_effective"],
            "side_effects_already_performed": ["ACTIVE_AUTHORITY_CLEARED"],
            "post_admission_association_state": "hold_effective",
        },
        "ESTOP": {
            "disposition_path": ["received", "admitted", "stop_latched"],
            "side_effects_already_performed": [
                "ACTIVE_AUTHORITY_CLEARED",
                "ESTOP_LATCHED",
            ],
            "post_admission_association_state": "stop_latched",
        },
    }
    if set(association_branches) != set(expected_association_shapes):
        raise ResultError("restrictive-effect association branch set drifted")
    for action, expected_shape in expected_association_shapes.items():
        branch = association_branches[action]
        if not isinstance(branch, dict):
            raise ResultError(
                f"restrictive-effect association branch is not an object for {action}"
            )
        _exact_keys(
            branch,
            {
                "admission_disposition_path",
                "disposition_path",
                "side_effects_already_performed",
                "post_admission_association_state",
                "additional_side_effect_performed",
                "physical_dag_transition_sequence",
                "arbiter_pending_operation_digest",
                "actuation_authority_domain_key_digest",
                "restrictive_token_id",
                "fence_epoch",
                "side_effect_record_digest",
                "physical_invocation_count",
                "arbiter_resolution_digest",
                "body_completion_digest",
                "journal_transition_kind",
                "journal_event_digest",
                "installed_journal_head_digest",
                "association_digest",
            },
            f"observer_capture.restrictive_effect_association_branches.{action}",
        )
        if (
            branch.get("admission_disposition_path") != ["received", "admitted"]
            or branch.get("disposition_path") != expected_shape["disposition_path"]
            or branch.get("side_effects_already_performed")
            != expected_shape["side_effects_already_performed"]
            or branch.get("post_admission_association_state")
            != expected_shape["post_admission_association_state"]
            or branch.get("additional_side_effect_performed") is not False
            or branch.get("physical_dag_transition_sequence")
            != [
                "arbiter_pending",
                "body_reservation_mirror",
                "physical_boundary_invocation",
                "arbiter_resolution",
                "body_completion",
            ]
            or branch.get("physical_invocation_count") != 1
            or not isinstance(branch.get("fence_epoch"), int)
            or branch["fence_epoch"] <= 0
            or branch.get("journal_transition_kind") != "post_admission_association"
            or branch.get("journal_event_digest") != branch.get("association_digest")
            or not isinstance(branch.get("restrictive_token_id"), str)
            or re.fullmatch(
                r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
                r"[89ab][0-9a-f]{3}-[0-9a-f]{12}",
                branch["restrictive_token_id"],
            )
            is None
            or not isinstance(branch.get("arbiter_pending_operation_digest"), str)
            or re.fullmatch(
                r"[0-9a-f]{64}",
                branch["arbiter_pending_operation_digest"],
            )
            is None
            or branch.get("actuation_authority_domain_key_digest") != domain_key_digest
            or not isinstance(branch.get("side_effect_record_digest"), str)
            or re.fullmatch(r"[0-9a-f]{64}", branch["side_effect_record_digest"])
            is None
            or not isinstance(branch.get("installed_journal_head_digest"), str)
            or re.fullmatch(
                r"[0-9a-f]{64}",
                branch["installed_journal_head_digest"],
            )
            is None
            or not isinstance(branch.get("arbiter_resolution_digest"), str)
            or re.fullmatch(r"[0-9a-f]{64}", branch["arbiter_resolution_digest"])
            is None
            or not isinstance(branch.get("body_completion_digest"), str)
            or re.fullmatch(r"[0-9a-f]{64}", branch["body_completion_digest"]) is None
            or not isinstance(branch.get("association_digest"), str)
            or re.fullmatch(r"[0-9a-f]{64}", branch["association_digest"]) is None
            or len(
                {
                    branch["arbiter_pending_operation_digest"],
                    branch["side_effect_record_digest"],
                    branch["arbiter_resolution_digest"],
                    branch["body_completion_digest"],
                    branch["association_digest"],
                    branch["installed_journal_head_digest"],
                }
            )
            != 6
        ):
            raise ResultError(
                f"restrictive-effect association branch drifted for {action}"
            )


@lru_cache(maxsize=1)
def _expected_freshness_acceptance_result() -> str:
    return json.dumps(
        freshness_acceptance_probe.build_result(),
        separators=(",", ":"),
        sort_keys=True,
    )


def _verify_freshness_acceptance_probe(value: Any) -> None:
    if not isinstance(value, dict):
        raise ResultError("freshness/acceptance result is not an object")
    if (
        value.get("schema") != "ncp.b01-freshness-acceptance-probe.v2"
        or value.get("probe") != "freshness_acceptance"
        or value.get("status") != "synthetic_pre_ratification_non_normative"
    ):
        raise ResultError("freshness/acceptance result identity drifted")
    if json.dumps(value, separators=(",", ":"), sort_keys=True) != (
        _expected_freshness_acceptance_result()
    ):
        raise ResultError(
            "freshness/acceptance probe failed deterministic semantic replay"
        )
    if value.get("counts") != {
        "baseline_cases": 547,
        "hostile_rejections": 369,
        "invariant_witnesses": 84,
        "registered_mutants": 144,
        "killed_mutants": 144,
        "surviving_mutants": 0,
    }:
        raise ResultError("freshness/acceptance coverage counts drifted")
    if value.get("campaign_case_counts") != {
        "active_watchdog": 8,
        "actuation_domain_binding": 40,
        "body_freshness": 254,
        "effect_journal": 33,
        "input_closedness": 69,
        "intent_freshness": 3,
        "ordinary_participant_admission_dag": 6,
        "retirement_closure": 18,
        "retirement_drain": 8,
        "semantic_state_closure": 37,
        "transport_acceptance": 9,
        "unified_physical_boundary": 62,
    } or value.get("campaign_hostile_rejection_counts") != {
        "active_watchdog": 0,
        "actuation_domain_binding": 35,
        "body_freshness": 198,
        "effect_journal": 1,
        "input_closedness": 69,
        "intent_freshness": 2,
        "ordinary_participant_admission_dag": 0,
        "retirement_closure": 12,
        "retirement_drain": 2,
        "semantic_state_closure": 37,
        "transport_acceptance": 8,
        "unified_physical_boundary": 5,
    }:
        raise ResultError("freshness/acceptance campaign counts drifted")
    if (
        value.get("semantic_result_sha256")
        != "b65472caa556971a89dfc8d1f8b23f1a280a83580de4a146bd04924d7b9cf3d3"
        or value.get("surviving_mutants") != []
    ):
        raise ResultError("freshness/acceptance semantic baseline drifted")
    if value.get("retirement_closure_model") != {
        "hold_states": [
            "NONE",
            "HOLD_PENDING",
            "HOLD_EFFECTIVE",
            "HOLD_OUTCOME_UNKNOWN",
            "HOLD_CYCLE_CONSUMED",
        ],
        "terminal_hold_states": [
            "HOLD_CYCLE_CONSUMED",
            "HOLD_EFFECTIVE",
            "HOLD_OUTCOME_UNKNOWN",
        ],
        "estop_floors": [
            "NONE",
            "ESTOP_LATCHED",
            "ESTOP_OUTCOME_UNKNOWN",
        ],
        "closure_branches": [
            "EXACT_ARBITER_RETIREMENT",
            "LOST_ARBITER_PHYSICAL_ISOLATION",
        ],
        "hold_pending_direct_finalization": "FORBIDDEN",
        "exact_arbiter_terminal_hold_result": "PRESERVE_EXACTLY",
        "lost_arbiter_pending_hold_result": "HOLD_OUTCOME_UNKNOWN",
        "estop_retirement_authorization": ("OPERATOR_RESET_AND_RETIRE_GENERATION"),
        "unknown_union_values": "REJECT",
        "finalization_revalidates_closure_evidence": True,
        "closure_evidence_identity": (
            "SAME_MACHINE_ISSUED_OBJECT_IN_MAP_AND_ISSUANCE_LEDGER"
        ),
        "physical_isolation_proof_identity": ("SAME_MACHINE_RETAINED_CAPABILITY"),
    }:
        raise ResultError("retirement closure model drifted")
    if value.get("actuation_authority_domain_model") != {
        "domain_key_type": "ActuationAuthorityDomainKey",
        "domain_keys_per_plant_generation": 1,
        "arbiter_mirror_cardinality": "SCALAR_EXACTLY_ONE",
        "mirror_set_permitted": False,
        "qualified_atomic_multi_actuator_domain_permitted": True,
        "max_actuators_per_domain": 8,
        "cross_domain_atomic_success_permitted": False,
        "independent_domain_session_rule": "DISTINCT_SESSIONS",
        "unknown_or_default_domain_key": "REJECT",
        "digest_policy": "LOWERCASE_SHA256_NONZERO",
        "authority_identifier_policy": ("BOUNDED_EXPLICIT_PRINTABLE_ASCII_NON_DEFAULT"),
        "authority_identifier_max_bytes": 256,
        "installed_selector": "InstalledActuationAuthorityDomainSelector",
        "global_registry_capacity": 4,
        "registry_selector_cardinality": "ONE_PER_JURISDICTION_INCARNATION",
        "enrolled_conflict_channels": [
            "active",
            "hold",
            "estop",
            "watchdog",
            "interlock",
            "reset",
            "shared_bus",
        ],
        "reservation_concurrency": "SINGLE_SELECTOR_CAS",
        "creation_receipt_binds_domain_key": True,
        "creation_receipt_version": "EXACT_NONNEGATIVE_INTEGER",
        "caller_selected_reservation_substitution": "REJECT",
        "disjoint_domains": "SERIALIZE_THEN_RESERVE_FOR_DISTINCT_SESSIONS",
        "selector_scope_type": "PhysicalActuationJurisdictionKey",
        "physical_actuation_jurisdiction_key": (
            freshness_acceptance_probe.PHYSICAL_ACTUATION_JURISDICTION_KEY
        ),
        "physical_actuation_jurisdiction_incarnation": (
            freshness_acceptance_probe.PHYSICAL_ACTUATION_JURISDICTION_INCARNATION
        ),
        "body_principal_scope": "ALL_ENROLLED_BODIES_IN_JURISDICTION",
        "live_selectors_per_jurisdiction_incarnation": 1,
        "live_jurisdiction_incarnations_per_key": 1,
        "topology_change_requirements": [
            "COMPLETE_DOMAIN_FENCE",
            "QUALIFIED_PHYSICAL_ISOLATION",
            "FULL_DOMAIN_REENROLLMENT",
        ],
    }:
        raise ResultError("actuation authority-domain model drifted")
    if value.get("input_closedness_model") != {
        "dataclass_policy": "EXACT_CLASS_NO_SUBCLASSES",
        "enum_policy": "EXACT_ENUM_CLASS_NO_RAW_SCALAR_ALIASES",
        "boolean_policy": "EXACT_BOOL_NOT_INTEGER",
        "integer_policy": "EXACT_INT_NOT_BOOL_OR_SUBCLASS",
        "string_policy": "EXACT_STRING_NOT_SUBCLASS",
        "container_policy": "EXACT_DECLARED_CONTAINER_AND_MEMBER_TYPES",
        "invalid_input_authority": "NONE_FAIL_CLOSED",
        "identifier_policy": "BOUNDED_EXPLICIT_PRINTABLE_ASCII_NON_DEFAULT",
        "identifier_max_bytes": 256,
        "retained_state_policy": (
            "EXACT_CLOSED_UNION_DERIVED_INDEXES_AND_ISSUER_PROVENANCE"
        ),
        "retained_capability_identity": {
            "effect_boundary_token": ("ISSUED_SLOT_COMMAND_AND_TRANSITION_PROVENANCE"),
            "restrictive_operation": "SAME_RETAINED_OBJECT",
            "retirement_closure_evidence": "SAME_MACHINE_ISSUED_OBJECT",
            "physical_isolation_proof": "SAME_MACHINE_RETAINED_OBJECT",
            "active_durable_state": ("SAME_RETAINED_OBJECT_AND_INSTALL_FINGERPRINT"),
            "actuation_domain_creation_receipt": "SAME_RETAINED_OBJECT",
            "retirement_drain_grant": "SAME_RETAINED_OBJECT",
            "retirement_drain_capacity_cut": ("SAME_MACHINE_RETAINED_OPERATION"),
            "retirement_drain_applied_operation": ("SAME_MACHINE_RETAINED_OPERATION"),
        },
    }:
        raise ResultError("freshness/acceptance input closedness model drifted")
    if value.get("retained_state_closure_model") != {
        "effect_journal": (
            "REPLAY_ISSUER_LINKED_RESERVATION_AND_COMPLETION_TRANSITIONS"
        ),
        "unified_physical_boundary": (
            "EXACT_COMMIT_PREFIX_DERIVED_COUNTERS_AND_ONE_USE_TOKEN"
        ),
        "retirement_closure": (
            "CLOSED_EVIDENCE_UNION_AND_DUAL_ISSUANCE_INDEX_IDENTITY"
        ),
        "active_boundary": ("CLOSED_STATE_UNION_AND_BOUNDARY_INSTALL_FINGERPRINT"),
        "actuation_domain_selector": (
            "RECOMPUTED_GENERATION_OWNER_AND_GLOBAL_CONFLICT_GRAPH"
        ),
        "retirement_drain": ("MACHINE_ISSUED_CAPACITY_CUT_GRANT_AND_APPLIED_OPERATION"),
        "authority_identifiers": ("MAX_256_BYTES_PRINTABLE_ASCII_NON_DEFAULT"),
        "invalid_or_inconsistent_state_authority": "NONE_FAIL_CLOSED",
    }:
        raise ResultError("freshness/acceptance retained-state model drifted")
    admission_dag = value.get("ordinary_participant_admission_dag")
    if not isinstance(admission_dag, dict):
        raise ResultError("ordinary participant admission DAG is absent")
    admission_artifacts = admission_dag.get("artifacts")
    if not isinstance(admission_artifacts, list):
        raise ResultError("ordinary participant admission artifacts are absent")
    admission_dependencies = {
        artifact.get("artifact"): artifact.get("depends_on")
        for artifact in admission_artifacts
        if isinstance(artifact, dict)
    }
    if (
        admission_dag.get("branch") != "INSTALL_FRESH_SELECTOR_WITH_NATIVE_GENESIS"
        or admission_dag.get("digest_graph") != "EXACT_ACYCLIC"
        or admission_dependencies.get(
            "AuthorityTransactionDomainParticipantAdmissionCommitment"
        )
        != ["OwnerAuthorizedNativeGenesisFact"]
        or admission_dependencies.get("AuthorityTransactionCASCondition")
        != [
            "AuthorityTransactionDomainParticipantAdmissionCommitment",
            "OwnerAuthorizedNativeGenesisFact",
            "NativeParticipantReadWriteSelectorIdentitySet",
        ]
        or {
            "CandidateNativeParticipantStateHead",
            "CandidateInstalledNativeParticipantSelector",
        }.intersection(
            admission_dependencies.get(
                "AuthorityTransactionDomainParticipantAdmissionCommitment",
                [],
            )
        )
        or "AuthorityTransactionCommitReceipt"
        not in admission_dependencies.get(
            "AuthorityTransactionDomainParticipantAdmissionReceipt",
            [],
        )
        or admission_dag.get("cycle_mutant")
        != "ordinary_participant_commitment_binds_candidate_head"
        or not any(
            isinstance(mutation, dict)
            and mutation.get("mutation")
            == "ordinary_participant_commitment_binds_candidate_head"
            and mutation.get("expected_violation")
            == "ordinary_participant_admission_digest_dag_acyclic"
            and mutation.get("killed") is True
            for mutation in value.get("mutation_matrix", [])
        )
    ):
        raise ResultError("ordinary participant admission DAG drifted")
    claims = value.get("claim_boundary")
    if (
        not isinstance(claims, dict)
        or claims.get("bounded_executable_counterexamples_only") is not True
        or claims.get("abstract_state_and_receipt_invariants_only") is not True
        or claims.get("capacity_action_is_fixture_profile_specific") is not True
        or claims.get("universal_safe_action_established") is not False
        or claims.get("restrictive_terminal_enum_selected") is not False
        or any(
            claims.get(field) is not False
            for field in {
                "normative_contract_changed",
                "adr_accepted",
                "implementation_or_refinement_proved",
                "interoperability_or_transport_qualified",
                "physical_safety_established",
                "production_deadline_evidence",
                "independent_review_satisfied",
                "external_gate_satisfied",
                "release_authorized",
            }
        )
    ):
        raise ResultError("freshness/acceptance claim boundary drifted")


@lru_cache(maxsize=1)
def _expected_source_issuance_index_probe_result() -> str:
    return json.dumps(
        source_issuance_index_probe.build_result(),
        separators=(",", ":"),
        sort_keys=True,
    )


def _verify_source_issuance_index_probe(value: Any) -> None:
    if not isinstance(value, dict):
        raise ResultError("source-issuance-index result is not an object")
    if json.dumps(value, separators=(",", ":"), sort_keys=True) != (
        _expected_source_issuance_index_probe_result()
    ):
        raise ResultError(
            "source-issuance-index probe failed deterministic semantic replay"
        )
    _exact_keys(
        value,
        {
            "schema",
            "scope",
            "claim_boundary",
            "counts",
            "semantic_digest",
        },
        "source_issuance_index_probe",
    )
    if (
        value["schema"] != "ncp.b01-source-issuance-index-probe.v1"
        or value["scope"] != "bounded-local-synthetic-counterexample-discovery"
        or value["claim_boundary"] != SOURCE_ISSUANCE_INDEX_CLAIM_BOUNDARY
        or value["semantic_digest"]
        != "cb36719f18ae78f2cc0a8fdb3f149ac31ed17a80968a15733228c2db65bd59a6"
        or value["counts"]
        != {
            "accepted_scenarios": 20,
            "invariants": 71,
            "rejected_hostile_cases": 188,
            "typed_artifacts": 77,
            "witnesses": 27,
        }
    ):
        raise ResultError(
            "source-issuance-index identity, coverage, or semantic digest drifted"
        )


def _verify_smt(value: Any) -> None:
    if not isinstance(value, dict):
        raise ResultError("SMT result is not an object")
    _exact_keys(
        value,
        {
            "schema",
            "scope",
            "z3_version",
            "z3_binary_sha256",
            "claim_boundary",
            "obligations",
            "mutation_kill_matrix",
            "counts",
        },
        "smt",
    )
    if (
        value["schema"] != "ncp.b01-preliminary-smt-result.v2"
        or value["scope"] != "narrow-pre-ratification-obligations"
        or value["z3_version"] != "Z3 version 4.16.0 - 64 bit"
        or value["z3_binary_sha256"] != _current_z3_binary_sha256()
        or value["claim_boundary"] != SMT_CLAIM_BOUNDARY
    ):
        raise ResultError("SMT identity, tool binary, or claim boundary drifted")
    expected_checks = {
        "smt/assessment_monotonicity.smt2": [
            (
                "unauthenticated_local_policy_change_without_widening",
                "unsat",
            ),
            ("authenticated_deny_removal_witness", "sat"),
            ("authenticated_applied_disposition_witness", "sat"),
            (
                "applied_deny_without_authenticated_applied_disposition",
                "unsat",
            ),
            ("qualified_profile_tightening_witness", "sat"),
            ("unauthenticated_raw_evidence", "unsat"),
            ("producer_requested_deny_without_profile", "unsat"),
            ("assessor_self_admitted_profile", "unsat"),
            ("missing_profile_qualification", "unsat"),
            ("abstained_or_ineligible_evidence", "unsat"),
            ("same_causal_revision_effect", "unsat"),
            ("unauthenticated_widening", "unsat"),
            ("deny_recovery_before_dwell", "unsat"),
        ],
        "smt/authority_handover.smt2": [
            ("grant_after_complete_cut_witness", "sat"),
            ("old_and_new_live_overlap", "unsat"),
        ],
        "smt/non_authority_inputs.smt2": [
            ("valid_body_authority_witness", "sat"),
            (
                "observer_pid_export_or_simulation_grant_cannot_replace_body_lease",
                "unsat",
            ),
        ],
        "smt/stale_admission.smt2": [
            ("exact_current_fence_witness", "sat"),
            ("stale_generation_admission", "unsat"),
        ],
    }
    obligations = value["obligations"]
    if not isinstance(obligations, list) or len(obligations) != len(expected_checks):
        raise ResultError("SMT obligation list is incomplete")
    observed_paths: set[str] = set()
    for index, obligation in enumerate(obligations):
        if not isinstance(obligation, dict):
            raise ResultError(f"SMT obligation {index} is not an object")
        _exact_keys(
            obligation,
            {
                "path",
                "source_sha256",
                "source_bytes",
                "elapsed_microseconds_local",
                "checks",
                "stdout_sha256",
                "command",
            },
            f"smt.obligations[{index}]",
        )
        path = obligation["path"]
        if path not in expected_checks or path in observed_paths:
            raise ResultError(f"SMT obligation path {path!r} is invalid or duplicate")
        observed_paths.add(path)
        source = (ROOT / path).read_bytes()
        if (
            obligation["source_bytes"] != len(source)
            or obligation["source_sha256"] != _sha256(source)
            or obligation["command"] != ["z3", "-T:5", "-in"]
        ):
            raise ResultError(f"SMT obligation source or command drifted for {path}")
        _nonnegative_int(
            obligation["elapsed_microseconds_local"],
            f"smt.obligations[{index}].elapsed_microseconds_local",
        )
        checks = obligation["checks"]
        if not isinstance(checks, list):
            raise ResultError(f"SMT checks are not a list for {path}")
        actual_checks: list[tuple[str, str]] = []
        for check_index, check in enumerate(checks):
            if not isinstance(check, dict):
                raise ResultError(f"SMT check {path}/{check_index} is not an object")
            _exact_keys(
                check,
                {"id", "expected", "actual"},
                f"smt.obligations[{index}].checks[{check_index}]",
            )
            if check["expected"] != check["actual"]:
                raise ResultError(f"SMT check expected/actual differs for {path}")
            actual_checks.append((check["id"], check["actual"]))
        if actual_checks != expected_checks[path]:
            raise ResultError(f"SMT check identities or results drifted for {path}")
        expected_stdout = "".join(f"{result}\n" for _, result in actual_checks)
        if obligation["stdout_sha256"] != _sha256(expected_stdout.encode("utf-8")):
            raise ResultError(f"SMT stdout identity drifted for {path}")
    if observed_paths != set(expected_checks):
        raise ResultError("SMT obligation paths differ from the checked set")
    counts = value["counts"]
    if counts != {
        "files": 4,
        "checks": 19,
        "mutations_killed": 13,
        "mutations_survived": 0,
    }:
        raise ResultError("SMT obligation or mutation matrix is incomplete")
    mutations = value["mutation_kill_matrix"]
    expected_mutations = {
        (
            "smt/assessment_monotonicity.smt2",
            "omit_unauthenticated_state_preservation",
        ),
        ("smt/assessment_monotonicity.smt2", "omit_recovery_dwell"),
        ("smt/assessment_monotonicity.smt2", "omit_evidence_authentication"),
        ("smt/assessment_monotonicity.smt2", "omit_profile_authentication"),
        (
            "smt/assessment_monotonicity.smt2",
            "omit_profile_issuer_independence",
        ),
        ("smt/assessment_monotonicity.smt2", "omit_profile_qualification"),
        ("smt/assessment_monotonicity.smt2", "omit_evidence_eligibility"),
        ("smt/assessment_monotonicity.smt2", "omit_causal_separation"),
        (
            "smt/assessment_monotonicity.smt2",
            "omit_disposition_authentication",
        ),
        ("smt/assessment_monotonicity.smt2", "omit_applied_outcome"),
        ("smt/authority_handover.smt2", "omit_old_revocation"),
        ("smt/non_authority_inputs.smt2", "observer_can_replace_body_lease"),
        ("smt/stale_admission.smt2", "omit_generation_fence"),
    }
    if not isinstance(mutations, list) or len(mutations) != len(expected_mutations):
        raise ResultError("SMT mutation entries are incomplete")
    mutation_identities: set[tuple[str, str]] = set()
    for index, mutation in enumerate(mutations):
        if not isinstance(mutation, dict):
            raise ResultError(f"SMT mutation {index} is not an object")
        _exact_keys(
            mutation,
            {"mutation_id", "path", "detected", "reason", "mutant_sha256"},
            f"smt.mutation_kill_matrix[{index}]",
        )
        path = mutation["path"]
        mutation_id = mutation["mutation_id"]
        identity = (path, mutation_id)
        if (
            path not in expected_checks
            or identity in mutation_identities
            or identity not in expected_mutations
            or mutation["detected"] is not True
            or not isinstance(mutation["reason"], str)
            or not mutation["reason"]
            or not isinstance(mutation["mutant_sha256"], str)
            or len(mutation["mutant_sha256"]) != 64
        ):
            raise ResultError(f"SMT mutation {index} is malformed or duplicate")
        mutation_identities.add(identity)
    if mutation_identities != expected_mutations:
        raise ResultError("SMT mutation identities differ from the checked set")


def _verify_timing(value: Any, label: str, *, unit_suffix: str) -> None:
    if not isinstance(value, dict):
        raise ResultError(f"{label} is not an object")
    expected = {
        "iterations",
        f"minimum_{unit_suffix}",
        f"median_{unit_suffix}",
        f"p95_{unit_suffix}" if unit_suffix == "us" else f"p99_{unit_suffix}",
        f"maximum_{unit_suffix}",
    }
    _exact_keys(value, expected, label)
    _positive_int(value["iterations"], f"{label}.iterations")
    for key in expected - {"iterations"}:
        _nonnegative_int(value[key], f"{label}.{key}")
    percentile_key = (
        f"p95_{unit_suffix}" if unit_suffix == "us" else f"p99_{unit_suffix}"
    )
    if not (
        value[f"minimum_{unit_suffix}"]
        <= value[f"median_{unit_suffix}"]
        <= value[percentile_key]
        <= value[f"maximum_{unit_suffix}"]
    ):
        raise ResultError(f"{label} timing summary is not monotonic")


def _verify_resources(value: Any) -> None:
    if not isinstance(value, dict):
        raise ResultError("resource result is not an object")
    _exact_keys(
        value,
        {
            "schema",
            "scope",
            "python",
            "platform",
            "outer_runtime_identity",
            "queue_isolation",
            "bounded_parser",
            "bounded_journal",
            "ed25519",
            "claim_boundary",
        },
        "resources",
    )
    if (
        value["schema"] != "ncp.b01-preliminary-resource-result.v2"
        or value["scope"] != "deterministic-structure-and-machine-local-screen"
        or value["claim_boundary"] != RESOURCE_CLAIM_BOUNDARY
        or value["python"] != platform.python_version()
        or value["platform"] != platform.platform()
        or value["outer_runtime_identity"] != _outer_runtime_identity()
    ):
        raise ResultError("resource result identity or claim boundary drifted")

    queue = value["queue_isolation"]
    if not isinstance(queue, dict):
        raise ResultError("queue isolation result is not an object")
    _exact_keys(
        queue,
        {
            "capacities",
            "offers_per_observer_plane",
            "idle_control_roundtrip",
            "loaded_control_roundtrip",
            "drops",
            "control_rejections",
            "action_state_preserved",
            "shared_budget_mutation_detected",
        },
        "resources.queue_isolation",
    )
    if (
        queue["capacities"]
        != {"control": 128, "observation": 64, "extension": 64, "action": 1}
        or queue["offers_per_observer_plane"] != 100_000
        or queue["drops"] != {"observation": 99_936, "extension": 99_936}
        or queue["control_rejections"] != 0
        or queue["action_state_preserved"] is not True
        or queue["shared_budget_mutation_detected"] is not True
    ):
        raise ResultError("queue-isolation structural result drifted")
    _verify_timing(
        queue["idle_control_roundtrip"],
        "resources.queue_isolation.idle_control_roundtrip",
        unit_suffix="ns",
    )
    _verify_timing(
        queue["loaded_control_roundtrip"],
        "resources.queue_isolation.loaded_control_roundtrip",
        unit_suffix="ns",
    )

    parser = value["bounded_parser"]
    if not isinstance(parser, dict):
        raise ResultError("bounded parser result is not an object")
    _exact_keys(
        parser,
        {
            "limits",
            "measurements",
            "exact_depth_accepted",
            "over_depth_rejected",
            "oversized_frame_rejected_before_semantics",
            "duplicate_decoded_key_rejected",
            "unterminated_frame_rejected",
            "unbounded_parser_mutation_detected",
        },
        "resources.bounded_parser",
    )
    if (
        not isinstance(parser["limits"], dict)
        or set(parser["limits"])
        != {
            "max_frame_bytes",
            "max_nesting_depth",
            "preliminary_peak_traced_budget_bytes",
            "preliminary_local_budget_us",
        }
        or parser["limits"]["preliminary_peak_traced_budget_bytes"] != 24 * 1024 * 1024
        or parser["limits"]["preliminary_local_budget_us"] != 2_000_000
        or any(
            parser[field] is not True
            for field in {
                "exact_depth_accepted",
                "over_depth_rejected",
                "oversized_frame_rejected_before_semantics",
                "duplicate_decoded_key_rejected",
                "unterminated_frame_rejected",
                "unbounded_parser_mutation_detected",
            }
        )
    ):
        raise ResultError("bounded-parser structural result drifted")
    measurements = parser["measurements"]
    if not isinstance(measurements, list) or len(measurements) != 2:
        raise ResultError("bounded-parser measurements are incomplete")
    for index, measurement in enumerate(measurements):
        if not isinstance(measurement, dict):
            raise ResultError(f"bounded-parser measurement {index} is not an object")
        _exact_keys(
            measurement,
            {"frame_bytes", "items", "elapsed_microseconds_local", "peak_traced_bytes"},
            f"resources.bounded_parser.measurements[{index}]",
        )
        _positive_int(measurement["frame_bytes"], "parser frame bytes")
        _positive_int(measurement["items"], "parser items")
        _nonnegative_int(
            measurement["elapsed_microseconds_local"], "parser elapsed time"
        )
        _positive_int(measurement["peak_traced_bytes"], "parser peak traced bytes")
        if (
            measurement["frame_bytes"] >= parser["limits"]["max_frame_bytes"]
            or measurement["elapsed_microseconds_local"]
            > parser["limits"]["preliminary_local_budget_us"]
            or measurement["peak_traced_bytes"]
            > parser["limits"]["preliminary_peak_traced_budget_bytes"]
        ):
            raise ResultError("bounded-parser measurement exceeded its local screen")
    if measurements[0]["frame_bytes"] >= measurements[1]["frame_bytes"]:
        raise ResultError("bounded-parser fixtures are not ordered by size")

    journal = value["bounded_journal"]
    if not isinstance(journal, dict):
        raise ResultError("bounded journal result is not an object")
    _exact_keys(
        journal,
        {
            "limits",
            "retained_entries",
            "encoded_entry_bytes",
            "snapshot_bytes",
            "snapshot_sha256",
            "first_rejected_sequence",
            "required_recovery_entries",
            "restart_replay_exact",
            "truncated_snapshot_rejected",
            "duplicate_snapshot_key_rejected",
            "silent_eviction_mutation_detected",
        },
        "resources.bounded_journal",
    )
    if (
        journal["limits"] != {"max_entries": 128, "max_encoded_bytes": 65_536}
        or journal["retained_entries"] != 128
        or journal["first_rejected_sequence"] != 129
        or journal["required_recovery_entries"] != 13
        or any(
            journal[field] is not True
            for field in {
                "restart_replay_exact",
                "truncated_snapshot_rejected",
                "duplicate_snapshot_key_rejected",
                "silent_eviction_mutation_detected",
            }
        )
        or not isinstance(journal["snapshot_sha256"], str)
        or len(journal["snapshot_sha256"]) != 64
    ):
        raise ResultError("bounded-journal structural result drifted")
    _positive_int(journal["encoded_entry_bytes"], "journal encoded bytes")
    _positive_int(journal["snapshot_bytes"], "journal snapshot bytes")
    if journal["encoded_entry_bytes"] > journal["limits"]["max_encoded_bytes"]:
        raise ResultError("bounded journal exceeded its byte limit")

    ed25519 = value["ed25519"]
    if not isinstance(ed25519, dict):
        raise ResultError("Ed25519 result is not an object")
    _exact_keys(
        ed25519,
        {
            "schema",
            "algorithm",
            "library",
            "pynacl_version",
            "python",
            "platform",
            "measurement_clocks",
            "clock_metadata",
            "execution_model",
            "runtime_project",
            "runtime_identity",
            "preliminary_single_verify_cpu_p95_budget_us",
            "largest_signing_input_bytes",
            "maximum_observed_thread_cpu_us",
            "maximum_observed_process_cpu_us",
            "maximum_observed_wall_us",
            "maximum_observed_thread_cpu_p95_us",
            "maximum_observed_process_cpu_p95_us",
            "cpu_p95_budget_detector_self_tested",
            "result_validator_self_tested",
            "runner",
            "cases",
            "claim_boundary",
        },
        "resources.ed25519",
    )
    if (
        ed25519["schema"] != "ncp.b01-preliminary-ed25519-resource-result.v4"
        or ed25519["algorithm"] != "Ed25519"
        or ed25519["library"] != "PyNaCl"
        or ed25519["pynacl_version"] != "1.6.2"
        or ed25519["measurement_clocks"]
        != {
            "budget": ["thread_time_ns", "process_time_ns"],
            "observational": "perf_counter_ns",
        }
        or ed25519["execution_model"] != "synchronous-pynacl-verify-key-call"
        or ed25519["preliminary_single_verify_cpu_p95_budget_us"] != 100_000
        or ed25519["largest_signing_input_bytes"] != 1_420_000
        or ed25519["cpu_p95_budget_detector_self_tested"] is not True
        or ed25519["result_validator_self_tested"] is not True
        or ed25519["platform"] != value["platform"]
        or ed25519["claim_boundary"] != ED25519_CLAIM_BOUNDARY
    ):
        raise ResultError("Ed25519 local-screen identity drifted")
    clocks = ed25519["clock_metadata"]
    if not isinstance(clocks, dict):
        raise ResultError("Ed25519 clock metadata is not an object")
    _exact_keys(
        clocks,
        {"thread_time", "process_time", "perf_counter"},
        "resources.ed25519.clock_metadata",
    )
    for name, clock in clocks.items():
        if not isinstance(clock, dict):
            raise ResultError(f"Ed25519 {name} clock metadata is not an object")
        _exact_keys(
            clock,
            {"adjustable", "implementation", "monotonic", "resolution_ns"},
            f"resources.ed25519.clock_metadata.{name}",
        )
        if (
            clock["adjustable"] is not False
            or clock["monotonic"] is not True
            or not isinstance(clock["implementation"], str)
            or not clock["implementation"]
            or _positive_int(
                clock["resolution_ns"],
                f"resources.ed25519.clock_metadata.{name}.resolution_ns",
            )
            < 1
        ):
            raise ResultError(f"Ed25519 {name} clock metadata drifted")
    current_crypto_environment = _current_crypto_environment()
    if (
        ed25519["python"]
        != current_crypto_environment["runtime_identity"]["python"]["version"]
    ):
        raise ResultError("Ed25519 Python version differs from its executed runtime")
    if clocks != current_crypto_environment["clock_metadata"]:
        raise ResultError("Ed25519 clock metadata differs from the measured clocks")
    if ed25519["runtime_identity"] != current_crypto_environment["runtime_identity"]:
        raise ResultError("Ed25519 executed runtime identity drifted")
    runtime_project = ed25519["runtime_project"]
    if not isinstance(runtime_project, dict):
        raise ResultError("Ed25519 runtime project is not an object")
    _exact_keys(
        runtime_project,
        {"pyproject", "lock"},
        "resources.ed25519.runtime_project",
    )
    runtime_paths = {
        "pyproject": (
            "prototypes/authenticated-ingress/signed-forwarding-envelope/pyproject.toml"
        ),
        "lock": ("prototypes/authenticated-ingress/signed-forwarding-envelope/uv.lock"),
    }
    for name, relative_path in runtime_paths.items():
        identity = runtime_project[name]
        if not isinstance(identity, dict):
            raise ResultError(f"Ed25519 runtime {name} identity is not an object")
        _exact_keys(
            identity,
            {"path", "sha256", "bytes"},
            f"resources.ed25519.runtime_project.{name}",
        )
        content = (REPOSITORY / relative_path).read_bytes()
        if identity != {
            "path": relative_path,
            "sha256": _sha256(content),
            "bytes": len(content),
        }:
            raise ResultError(f"Ed25519 runtime {name} identity drifted")
    runner = ed25519["runner"]
    if not isinstance(runner, dict):
        raise ResultError("Ed25519 runner identity is not an object")
    _exact_keys(
        runner,
        {"tool", "version", "executable_sha256", "invocation"},
        "resources.ed25519.runner",
    )
    uv = shutil.which("uv")
    uv_version = (
        subprocess.run(  # noqa: S603
            [uv, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if uv is not None
        else None
    )
    if (
        uv is None
        or runner["tool"] != "uv"
        or uv_version is None
        or uv_version.returncode != 0
        or uv_version.stderr
        or runner["version"] != uv_version.stdout.strip()
        or runner["executable_sha256"] != _sha256(Path(uv).read_bytes())
        or runner["invocation"]
        != [
            "run",
            "--no-sync",
            "--offline",
            "--locked",
            "--project",
            "prototypes/authenticated-ingress/signed-forwarding-envelope",
            "python",
            "-I",
            "prototypes/b01-architecture-evidence/crypto_probe.py",
            "--self-test",
        ]
    ):
        raise ResultError("Ed25519 runner identity drifted")
    maximum_thread_cpu = _nonnegative_int(
        ed25519["maximum_observed_thread_cpu_us"],
        "Ed25519 maximum observed thread CPU time",
    )
    maximum_process_cpu = _nonnegative_int(
        ed25519["maximum_observed_process_cpu_us"],
        "Ed25519 maximum observed process CPU time",
    )
    maximum_wall = _nonnegative_int(
        ed25519["maximum_observed_wall_us"],
        "Ed25519 maximum observed wall time",
    )
    maximum_thread_cpu_p95 = _nonnegative_int(
        ed25519["maximum_observed_thread_cpu_p95_us"],
        "Ed25519 maximum observed thread CPU p95",
    )
    maximum_process_cpu_p95 = _nonnegative_int(
        ed25519["maximum_observed_process_cpu_p95_us"],
        "Ed25519 maximum observed process CPU p95",
    )
    if (
        max(maximum_thread_cpu_p95, maximum_process_cpu_p95)
        > ed25519["preliminary_single_verify_cpu_p95_budget_us"]
    ):
        raise ResultError("Ed25519 CPU-p95 screen exceeded its declared budget")
    cases = ed25519["cases"]
    expected_cases = [
        ("empty", 0, 300),
        ("64k", 65_536, 150),
        ("max_profile_input", 1_420_000, 40),
    ]
    if not isinstance(cases, list) or len(cases) != len(expected_cases):
        raise ResultError("Ed25519 local-screen cases are incomplete")
    for index, (case, expected) in enumerate(zip(cases, expected_cases, strict=True)):
        if not isinstance(case, dict):
            raise ResultError(f"Ed25519 case {index} is not an object")
        _exact_keys(
            case,
            {
                "case",
                "message_bytes",
                "valid_thread_cpu",
                "invalid_full_length_thread_cpu",
                "valid_process_cpu",
                "invalid_full_length_process_cpu",
                "valid_wall",
                "invalid_full_length_wall",
            },
            f"resources.ed25519.cases[{index}]",
        )
        label, message_bytes, iterations = expected
        if case["case"] != label or case["message_bytes"] != message_bytes:
            raise ResultError(f"Ed25519 case identity drifted for {label}")
        _verify_timing(
            case["valid_thread_cpu"],
            f"resources.ed25519.cases[{index}].valid_thread_cpu",
            unit_suffix="us",
        )
        _verify_timing(
            case["invalid_full_length_thread_cpu"],
            f"resources.ed25519.cases[{index}].invalid_full_length_thread_cpu",
            unit_suffix="us",
        )
        _verify_timing(
            case["valid_process_cpu"],
            f"resources.ed25519.cases[{index}].valid_process_cpu",
            unit_suffix="us",
        )
        _verify_timing(
            case["invalid_full_length_process_cpu"],
            f"resources.ed25519.cases[{index}].invalid_full_length_process_cpu",
            unit_suffix="us",
        )
        _verify_timing(
            case["valid_wall"],
            f"resources.ed25519.cases[{index}].valid_wall",
            unit_suffix="us",
        )
        _verify_timing(
            case["invalid_full_length_wall"],
            f"resources.ed25519.cases[{index}].invalid_full_length_wall",
            unit_suffix="us",
        )
        if (
            any(
                case[field]["iterations"] != iterations
                for field in {
                    "valid_thread_cpu",
                    "invalid_full_length_thread_cpu",
                    "valid_process_cpu",
                    "invalid_full_length_process_cpu",
                    "valid_wall",
                    "invalid_full_length_wall",
                }
            )
            or max(
                case["valid_thread_cpu"]["p95_us"],
                case["invalid_full_length_thread_cpu"]["p95_us"],
                case["valid_process_cpu"]["p95_us"],
                case["invalid_full_length_process_cpu"]["p95_us"],
            )
            > ed25519["preliminary_single_verify_cpu_p95_budget_us"]
        ):
            raise ResultError(f"Ed25519 case timing drifted for {label}")
    observed_thread_cpu_maxima = [
        case[field]["maximum_us"]
        for case in cases
        for field in {"valid_thread_cpu", "invalid_full_length_thread_cpu"}
    ]
    observed_process_cpu_maxima = [
        case[field]["maximum_us"]
        for case in cases
        for field in {"valid_process_cpu", "invalid_full_length_process_cpu"}
    ]
    observed_wall_maxima = [
        case[field]["maximum_us"]
        for case in cases
        for field in {"valid_wall", "invalid_full_length_wall"}
    ]
    observed_thread_cpu_p95 = [
        case[field]["p95_us"]
        for case in cases
        for field in {"valid_thread_cpu", "invalid_full_length_thread_cpu"}
    ]
    observed_process_cpu_p95 = [
        case[field]["p95_us"]
        for case in cases
        for field in {"valid_process_cpu", "invalid_full_length_process_cpu"}
    ]
    if (
        maximum_thread_cpu != max(observed_thread_cpu_maxima)
        or maximum_process_cpu != max(observed_process_cpu_maxima)
        or maximum_wall != max(observed_wall_maxima)
        or maximum_thread_cpu_p95 != max(observed_thread_cpu_p95)
        or maximum_process_cpu_p95 != max(observed_process_cpu_p95)
    ):
        raise ResultError("Ed25519 aggregate timing maxima drifted")


def verify(value: dict[str, Any]) -> None:
    _exact_keys(
        value,
        {
            "schema",
            "scope",
            "task",
            "candidate",
            "wire_version",
            "source_commit",
            "source_tree",
            "source_paths_clean",
            "source_status",
            "repository_clean",
            "repository_status",
            "generated_at_utc",
            "fable_advice_response_sha256",
            "normative_contract_sha256",
            "contract_manifest_sha256",
            "compact_contract_hash",
            "sources",
            "adr_example_semantics",
            "decision_probe",
            "observer_authorization_probe",
            "observer_capture_probe",
            "freshness_acceptance_probe",
            "source_issuance_index_probe",
            "model",
            "smt",
            "resources",
            "claim_boundary",
        },
        "result",
    )
    if (
        value.get("schema") != "ncp.b01-preliminary-architecture-evidence.v3"
        or value.get("scope") != "proposed-adrs-only"
        or value.get("task") != "B01"
        or value.get("candidate") != "1.0.0-rc.1"
        or value.get("wire_version") != "1.0"
    ):
        raise ResultError("result identity differs from the checked B01 prototype")
    if value.get("source_paths_clean") is not True or value.get("source_status") != []:
        raise ResultError("result was not generated from clean prototype source paths")
    if (
        value.get("repository_clean") is not True
        or value.get("repository_status") != []
    ):
        raise ResultError("result was not generated from a clean repository")
    relative_root = str(ROOT.relative_to(REPOSITORY))
    if _git("status", "--short", "--", relative_root) != "":
        raise ResultError("current prototype source paths are not clean")
    if _git("status", "--short") != "":
        raise ResultError("current repository is not clean")
    if value.get("source_commit") != _git("rev-parse", "HEAD"):
        raise ResultError("result source commit differs from current HEAD")
    if value.get("source_tree") != _git("rev-parse", "HEAD^{tree}"):
        raise ResultError("result source tree differs from current HEAD")
    if value.get("fable_advice_response_sha256") != EXPECTED_FABLE_SHA256:
        raise ResultError("Fable advice response identity drifted")
    if value.get("normative_contract_sha256") != EXPECTED_CONTRACT_SHA256:
        raise ResultError("normative contract digest changed")
    if value.get("contract_manifest_sha256") != _current_contract_manifest_sha256():
        raise ResultError("current contract manifest bytes changed")
    if value.get("compact_contract_hash") != "163acc57d8a62b66":
        raise ResultError("compact contract hash changed")
    if (REPOSITORY / "contract/decision-registry.v1.json").exists():
        raise ResultError("normative decision registry was created prematurely")
    _verify_timestamp(value.get("generated_at_utc"))
    _verify_sources(value)
    _verify_adr_example_semantics(value["adr_example_semantics"])
    _verify_decision_probe(value["decision_probe"])
    _verify_observer_authorization_probe(value["observer_authorization_probe"])
    _verify_observer_capture_probe(value["observer_capture_probe"])
    _verify_freshness_acceptance_probe(value["freshness_acceptance_probe"])
    _verify_source_issuance_index_probe(value["source_issuance_index_probe"])
    _verify_model(value["model"])
    _verify_smt(value["smt"])
    _verify_resources(value["resources"])

    claims = value["claim_boundary"]
    _exact_keys(
        claims,
        {
            "adrs_accepted",
            "normative_contract_changed",
            "canonical_formal_task_started",
            "implementation_or_refinement_proved",
            "independent_review_satisfied",
            "external_gate_satisfied",
            "release_authorized",
            "strongest_local_statement",
        },
        "claim_boundary",
    )
    expected_false = {
        "adrs_accepted",
        "normative_contract_changed",
        "canonical_formal_task_started",
        "implementation_or_refinement_proved",
        "independent_review_satisfied",
        "external_gate_satisfied",
        "release_authorized",
    }
    if any(claims.get(field) is not False for field in expected_false):
        raise ResultError("claim boundary contains an optimistic statement")
    semantic_result = value["adr_example_semantics"]
    expected_statement = _strongest_local_statement(
        semantic_result["case_count"], semantic_result["mutation_count"]
    )
    if claims.get("strongest_local_statement") != expected_statement:
        raise ResultError("strongest local statement drifted")
    if (
        _git("status", "--short", "--", relative_root) != ""
        or _git("status", "--short") != ""
        or value.get("source_commit") != _git("rev-parse", "HEAD")
        or value.get("source_tree") != _git("rev-parse", "HEAD^{tree}")
        or value.get("contract_manifest_sha256") != _current_contract_manifest_sha256()
    ):
        raise ResultError("repository identity changed during verification")
    _verify_sources(value)


def _self_test(value: dict[str, Any]) -> int:
    mutations = (
        ("release claim", ("claim_boundary", "release_authorized"), True),
        ("contract digest", ("normative_contract_sha256",), "0" * 64),
        ("contract manifest", ("contract_manifest_sha256",), "0" * 64),
        ("source digest", ("sources", 0, "sha256"), "0" * 64),
        (
            "source path",
            ("sources", 0, "path"),
            "prototypes/b01-architecture-evidence/FORGED.py",
        ),
        ("source count", ("sources",), value["sources"][:-1]),
        (
            "ADR semantic independent-evidence claim",
            (
                "adr_example_semantics",
                "claim_boundary",
                "independent_evidence_satisfied",
            ),
            True,
        ),
        (
            "ADR semantic case count",
            ("adr_example_semantics", "case_count"),
            24,
        ),
        (
            "ADR semantic mutation count",
            ("adr_example_semantics", "mutation_count"),
            value["adr_example_semantics"]["mutation_count"] - 1,
        ),
        (
            "ADR semantic parity digest",
            ("adr_example_semantics", "semantic_parity_sha256"),
            "0" * 64,
        ),
        (
            "ADR semantic exact match",
            ("adr_example_semantics", "exact_semantic_match"),
            False,
        ),
        (
            "ADR semantic Rust source digest",
            (
                "adr_example_semantics",
                "engine_source_identities",
                "rust",
                0,
                "sha256",
            ),
            "0" * 64,
        ),
        (
            "ADR semantic coordinator detection count",
            (
                "adr_example_semantics",
                "coordinator_self_tests",
                "detected",
            ),
            0,
        ),
        (
            "ADR semantic source-tree output claim",
            ("adr_example_semantics", "source_tree_build_output_absent"),
            False,
        ),
        ("repository clean", ("repository_clean",), False),
        ("stale timestamp", ("generated_at_utc",), "1970-01-01T00:00:00Z"),
        ("model claim", ("model", "claim_boundary"), "release proven"),
        ("model survivor", ("model", "counts", "mutations_survived"), 1),
        (
            "decision probe survivor",
            ("decision_probe", "counts", "fault_cases_survived"),
            1,
        ),
        (
            "observer authorization hostile coverage",
            (
                "observer_authorization_probe",
                "counts",
                "hostile_rejections",
            ),
            EXPECTED_OBSERVER_AUTHORIZATION_COUNTS["hostile_rejections"] - 1,
        ),
        (
            "observer authorization release claim",
            (
                "observer_authorization_probe",
                "claim_boundary",
                "release_readiness",
            ),
            "PASS",
        ),
        (
            "observer capture hostile coverage",
            ("observer_capture_probe", "counts", "hostile_inputs_rejected"),
            441,
        ),
        (
            "observer capture capsule mints future authority",
            (
                "observer_capture_probe",
                "grant_lifecycle",
                "observer_read_capture_bridge",
                "future_read_authority_from_capsule",
            ),
            True,
        ),
        (
            "observer capture omits one semantic axis",
            (
                "observer_capture_probe",
                "grant_lifecycle",
                "observer_read_capture_bridge",
                "capsule_backed_current_axis_slots",
            ),
            ["A", "D", "V"],
        ),
        (
            "observer capture synthetic contrast mislabeled as mutant",
            ("observer_capture_probe", "counts", "logic_mutants_killed"),
            1,
        ),
        (
            "observer capture semantic contrast coverage",
            (
                "observer_capture_probe",
                "counts",
                "semantic_contrasts_reached",
            ),
            14,
        ),
        (
            "observer capture selector overclaim",
            (
                "observer_capture_probe",
                "capture_action",
                "selector_evidence_qualification",
                "status",
            ),
            "QUALIFIED_AS_SELECTOR_CLOSURE_EVIDENCE",
        ),
        (
            "observer capture local-outbox transport conflation",
            (
                "observer_capture_probe",
                "capture_action",
                "haldir_publication_boundaries",
                "local_atomic_result",
            ),
            "ACCEPTED_BY_NCP_TRANSPORT",
        ),
        (
            "observer capture HOLD association repeats effect",
            (
                "observer_capture_probe",
                "capture_action",
                "restrictive_effect_association_branches",
                "HOLD",
                "additional_side_effect_performed",
            ),
            True,
        ),
        (
            "observer capture admission skips association",
            (
                "observer_capture_probe",
                "capture_action",
                "restrictive_effect_association_branches",
                "HOLD",
                "admission_disposition_path",
            ),
            ["received", "admitted", "hold_effective"],
        ),
        (
            "observer capture physical DAG omits mirror",
            (
                "observer_capture_probe",
                "capture_action",
                "restrictive_effect_association_branches",
                "HOLD",
                "physical_dag_transition_sequence",
            ),
            [
                "arbiter_pending",
                "physical_boundary_invocation",
                "arbiter_resolution",
                "body_completion",
            ],
        ),
        (
            "freshness acceptance survivor",
            ("freshness_acceptance_probe", "counts", "surviving_mutants"),
            1,
        ),
        (
            "freshness transport overclaim",
            (
                "freshness_acceptance_probe",
                "claim_boundary",
                "interoperability_or_transport_qualified",
            ),
            True,
        ),
        (
            "freshness unified DAG campaign omitted",
            (
                "freshness_acceptance_probe",
                "campaign_case_counts",
                "unified_physical_boundary",
            ),
            0,
        ),
        (
            "freshness universal safe action overclaim",
            (
                "freshness_acceptance_probe",
                "claim_boundary",
                "universal_safe_action_established",
            ),
            True,
        ),
        (
            "source-index hostile coverage",
            (
                "source_issuance_index_probe",
                "counts",
                "rejected_hostile_cases",
            ),
            91,
        ),
        (
            "source-index semantic digest",
            ("source_issuance_index_probe", "semantic_digest"),
            "0" * 64,
        ),
        (
            "source-index proof overclaim",
            ("source_issuance_index_probe", "claim_boundary"),
            "protocol correctness proven",
        ),
        ("SMT survivor", ("smt", "counts", "mutations_survived"), 1),
        (
            "queue detector",
            ("resources", "queue_isolation", "shared_budget_mutation_detected"),
            False,
        ),
        (
            "Ed25519 process-CPU p95 budget",
            ("resources", "ed25519", "maximum_observed_process_cpu_p95_us"),
            100_001,
        ),
        (
            "Ed25519 budget clock",
            ("resources", "ed25519", "measurement_clocks", "budget"),
            "perf_counter_ns",
        ),
        (
            "Ed25519 runtime lock",
            ("resources", "ed25519", "runtime_project", "lock", "sha256"),
            "0" * 64,
        ),
        ("resource Python", ("resources", "python"), "FORGED"),
        ("resource platform", ("resources", "platform"), "FORGED"),
        (
            "resource Python executable",
            (
                "resources",
                "outer_runtime_identity",
                "executable",
                "sha256",
            ),
            "0" * 64,
        ),
        ("Ed25519 Python", ("resources", "ed25519", "python"), "FORGED"),
        ("Ed25519 platform", ("resources", "ed25519", "platform"), "FORGED"),
        (
            "Ed25519 thread clock implementation",
            (
                "resources",
                "ed25519",
                "clock_metadata",
                "thread_time",
                "implementation",
            ),
            "FORGED",
        ),
        (
            "Ed25519 Python executable",
            (
                "resources",
                "ed25519",
                "runtime_identity",
                "python",
                "executable",
                "sha256",
            ),
            "0" * 64,
        ),
        (
            "Ed25519 native sodium artifact",
            (
                "resources",
                "ed25519",
                "runtime_identity",
                "loaded_native_artifacts",
                "pynacl_sodium",
                "sha256",
            ),
            "0" * 64,
        ),
        (
            "Ed25519 claim boundary",
            ("resources", "ed25519", "claim_boundary"),
            "production deadline proven",
        ),
    )
    rejected = 0
    for label, path, replacement in mutations:
        hostile = copy.deepcopy(value)
        cursor: Any = hostile
        for member in path[:-1]:
            cursor = cursor[member]
        cursor[path[-1]] = replacement
        try:
            verify(hostile)
        except ResultError:
            rejected += 1
            continue
        raise ResultError(f"self-test accepted hostile mutation: {label}")

    hostile = copy.deepcopy(value)
    hostile["model"]["optimistic_extra_claim"] = "release proven"
    try:
        verify(hostile)
    except ResultError:
        rejected += 1
    else:
        raise ResultError("self-test accepted an unknown nested claim")

    for omitted in (
        "adr_example_semantics",
        "freshness_acceptance_probe",
        "source_issuance_index_probe",
    ):
        hostile = copy.deepcopy(value)
        del hostile[omitted]
        try:
            verify(hostile)
        except ResultError:
            rejected += 1
            continue
        raise ResultError(f"self-test accepted an omitted {omitted}")
    return rejected


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--decision-only", action="store_true")
    mode.add_argument("--observer-authorization-only", action="store_true")
    mode.add_argument("--adr-example-semantics-only", action="store_true")
    args = parser.parse_args()
    if args.adr_example_semantics_only:
        semantic_value = _load_adr_example_semantics()
        _verify_adr_example_semantics(semantic_value)
        print(
            "OK B01 ADR-example semantics: "
            f"{semantic_value['case_count']} exact cases, "
            f"{semantic_value['mutation_count']} bounded mutations, "
            f"{semantic_value['coordinator_self_tests']['detected']} coordinator "
            "controls; PROPOSED only, no independent or release claim"
        )
        return 0
    if args.decision_only:
        decision_value = _load_decision_probe()
        _verify_decision_probe(decision_value)
        counts = decision_value["counts"]
        print(
            "OK B01 decision probe: "
            f"{counts['finite_cases_evaluated']} finite cases, "
            f"{counts['logic_mutants_killed']} executable logic mutants, "
            f"{counts['semantic_contrasts_reached']} semantic contrasts, "
            f"{counts['hostile_inputs_rejected']} hostile inputs, "
            f"{counts['invariant_witnesses_reached']} invariant witnesses; "
            "PROPOSED only, no independent or release claim"
        )
        return 0
    if args.observer_authorization_only:
        authorization_value = _load_observer_authorization_probe()
        _verify_observer_authorization_probe(authorization_value)
        counts = authorization_value["counts"]
        print(
            "OK B01 observer authorization probe: "
            f"{counts['hostile_rejections']} hostile inputs, "
            f"{counts['registered_staged_artifact_types']} staged artifact types, "
            f"{counts['release_linearization_witnesses']} release witnesses; "
            "PROPOSED only, no independent or release claim"
        )
        return 0
    value = _load()
    verify(value)
    verifier_mutations_rejected = _self_test(value) if args.self_test else 0
    canonical = json.dumps(value, separators=(",", ":"), sort_keys=True)
    print(PREFIX + canonical)
    print(
        "OK B01 preliminary evidence: "
        f"{value['model']['composition']['states']} composition states, "
        f"{value['model']['counts']['mutations_killed']} model mutations, "
        f"{value['decision_probe']['counts']['logic_mutants_killed']} decision "
        "executable logic mutants, "
        f"{value['decision_probe']['counts']['semantic_contrasts_reached']} "
        "decision semantic contrasts, "
        f"{value['decision_probe']['counts']['hostile_inputs_rejected']} decision "
        "hostile inputs, "
        f"{value['observer_authorization_probe']['counts']['hostile_rejections']} "
        "authorization hostile inputs, "
        f"{value['observer_capture_probe']['counts']['hostile_inputs_rejected']} "
        "observer/capture hostile inputs, "
        f"{value['freshness_acceptance_probe']['counts']['baseline_cases']} "
        "freshness/acceptance cases, "
        f"{value['freshness_acceptance_probe']['counts']['killed_mutants']} "
        "freshness/acceptance mutants, "
        f"{value['source_issuance_index_probe']['counts']['rejected_hostile_cases']} "
        "source-index hostile cases, "
        f"{value['source_issuance_index_probe']['counts']['invariants']} "
        "source-index invariants, "
        f"{value['adr_example_semantics']['case_count']} ADR-example semantic cases, "
        f"{value['adr_example_semantics']['mutation_count']} ADR-example semantic "
        "mutations rejected, "
        f"{value['smt']['counts']['checks']} SMT checks, "
        f"{value['smt']['counts']['mutations_killed']} SMT mutations"
        + (
            f", {verifier_mutations_rejected} verifier hostile mutations rejected"
            if args.self_test
            else ""
        )
        + "; PROPOSED only, no independent or release claim"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, TypeError, ValueError, ResultError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
