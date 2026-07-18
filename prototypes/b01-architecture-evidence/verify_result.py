#!/usr/bin/env python3
"""Fail-closed verifier for one B01 preliminary architecture-evidence result."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PREFIX = "NCP_B01_PRELIMINARY_RESULT="
MAX_RESULT_BYTES = 2_000_000
EXPECTED_CONTRACT_SHA256 = (
    "9cae331742d01e9b164e029aa06c644e6b1886176d0816a6ef883af138355c90"
)
EXPECTED_FABLE_SHA256 = (
    "080ad93775d6dec018a08efeadd49b0d57e6162a90f4bc7cf9a8b43199246d32"
)
SOURCE_SUFFIXES = {".py", ".sh", ".smt2", ".md"}
MAX_RESULT_AGE = timedelta(hours=1)
MAX_RESULT_FUTURE_SKEW = timedelta(minutes=5)
STRONGEST_LOCAL_STATEMENT = (
    "No counterexample was found within the recorded finite models and fixed "
    "local resource corpus; every registered seeded mutation was detected."
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
RESOURCE_CLAIM_BOUNDARY = (
    "These probes exercise explicit prototype bounds and one local machine. "
    "They do not select normative capacities, prove production deadlines, "
    "qualify performance, establish durability, certify safety, or close any "
    "external release gate."
)
UTC_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{6})?Z$"
)


class ResultError(RuntimeError):
    """One malformed, stale, optimistic, incomplete, or unbounded result."""


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, member in pairs:
        if key in value:
            raise ResultError(f"duplicate JSON key {key!r}")
        value[key] = member
    return value


def _reject_json_constant(value: str) -> None:
    raise ResultError(f"non-finite JSON constant {value!r}")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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
    path = REPOSITORY / "contract/manifest.v1.json"
    content = path.read_bytes()
    value = json.loads(
        content,
        object_pairs_hook=_object_no_duplicates,
        parse_constant=_reject_json_constant,
    )
    if (
        not isinstance(value, dict)
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
        value = json.loads(
            text[len(PREFIX) :],
            object_pairs_hook=_object_no_duplicates,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as error:
        raise ResultError("result is not strict JSON") from error
    if not isinstance(value, dict):
        raise ResultError("result root is not an object")
    return value


def _verify_sources(value: dict[str, Any]) -> None:
    sources = value["sources"]
    if not isinstance(sources, list) or len(sources) < 10:
        raise ResultError("source inventory is incomplete")
    paths: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise ResultError(f"sources[{index}] is not an object")
        _exact_keys(source, {"path", "bytes", "sha256"}, f"sources[{index}]")
        path = source["path"]
        if (
            not isinstance(path, str)
            or not path.startswith("prototypes/b01-architecture-evidence/")
            or path in paths
        ):
            raise ResultError(f"sources[{index}].path is invalid or duplicate")
        paths.add(path)
        content = (REPOSITORY / path).read_bytes()
        if source["bytes"] != len(content) or source["sha256"] != _sha256(content):
            raise ResultError(f"source identity drifted for {path}")
    expected_paths = {
        path.relative_to(REPOSITORY).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and path.suffix in SOURCE_SUFFIXES
    }
    if paths != expected_paths:
        raise ResultError(
            "source inventory does not equal the checked prototype source set"
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
        value["schema"] != "ncp.b01-preliminary-model-result.v1"
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
            "recover_body",
            "restart_body",
            "restart_stream",
        },
        expected_witnesses={
            "delayed_stale_rejected_while_fresh_command_pending",
            "direct_to_gated_handover_completed",
            "fresh_command_applied",
            "hostile_or_stale_command_rejected",
            "restart_or_expiry_recovered",
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
            "apply_deny",
            "assessor_allow_attempt",
            "authenticated_base_widen",
            "authenticated_widen",
            "base_policy_deny",
            "disable",
            "expire",
            "record_only",
            "restart",
            "retract",
            "unauthenticated_base_widen",
            "unauthenticated_clear",
            "unauthenticated_deny_attempt",
        },
        expected_witnesses={
            "authenticated_base_widen_succeeded",
            "authenticated_deny_applied",
            "authenticated_deny_removal_succeeded",
            "disable_remains_non_widening",
            "expire_remains_non_widening",
            "record_only_is_identity",
            "restart_preserved_applied_deny",
            "retract_remains_non_widening",
            "unauthenticated_deny_tightening_blocked",
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
        "mutations_killed": 23,
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
        ("deny_lifecycle", "expiry_clears"),
        ("deny_lifecycle", "retraction_clears"),
        ("deny_lifecycle", "disable_clears"),
        ("deny_lifecycle", "restart_drops"),
        ("deny_lifecycle", "unauthenticated_clear"),
        ("deny_lifecycle", "record_only_clears"),
        ("deny_lifecycle", "assessor_allows"),
        ("deny_lifecycle", "unauthenticated_deny_applies"),
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
        value["schema"] != "ncp.b01-preliminary-smt-result.v1"
        or value["scope"] != "narrow-pre-ratification-obligations"
        or value["z3_version"] != "Z3 version 4.16.0 - 64 bit"
        or value["z3_binary_sha256"] != _current_z3_binary_sha256()
        or value["claim_boundary"] != SMT_CLAIM_BOUNDARY
    ):
        raise ResultError("SMT identity, tool binary, or claim boundary drifted")
    expected_checks = {
        "smt/assessment_monotonicity.smt2": [
            ("authenticated_deny_removal_witness", "sat"),
            ("authenticated_applied_disposition_witness", "sat"),
            (
                "applied_deny_without_authenticated_applied_disposition",
                "unsat",
            ),
            ("assessor_tightening_witness", "sat"),
            ("unauthenticated_widening", "unsat"),
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
            or obligation["command"] != ["z3", "-T:5", "<obligation>"]
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
        "checks": 11,
        "mutations_killed": 4,
        "mutations_survived": 0,
    }:
        raise ResultError("SMT obligation or mutation matrix is incomplete")
    mutations = value["mutation_kill_matrix"]
    if not isinstance(mutations, list) or len(mutations) != 4:
        raise ResultError("SMT mutation entries are incomplete")
    mutation_paths: set[str] = set()
    for index, mutation in enumerate(mutations):
        if not isinstance(mutation, dict):
            raise ResultError(f"SMT mutation {index} is not an object")
        _exact_keys(
            mutation,
            {"path", "detected", "reason", "mutant_sha256"},
            f"smt.mutation_kill_matrix[{index}]",
        )
        path = mutation["path"]
        if (
            path not in expected_checks
            or path in mutation_paths
            or mutation["detected"] is not True
            or not isinstance(mutation["reason"], str)
            or not mutation["reason"]
            or not isinstance(mutation["mutant_sha256"], str)
            or len(mutation["mutant_sha256"]) != 64
        ):
            raise ResultError(f"SMT mutation {index} is malformed or duplicate")
        mutation_paths.add(path)
    if mutation_paths != set(expected_checks):
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
            "queue_isolation",
            "bounded_parser",
            "bounded_journal",
            "ed25519",
            "claim_boundary",
        },
        "resources",
    )
    if (
        value["schema"] != "ncp.b01-preliminary-resource-result.v1"
        or value["scope"] != "deterministic-structure-and-machine-local-screen"
        or value["claim_boundary"] != RESOURCE_CLAIM_BOUNDARY
        or not isinstance(value["python"], str)
        or not value["python"]
        or not isinstance(value["platform"], str)
        or not value["platform"]
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
        journal["limits"] != {"max_entries": 128, "max_encoded_entry_bytes": 65_536}
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
    if journal["encoded_entry_bytes"] > journal["limits"]["max_encoded_entry_bytes"]:
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
            "preliminary_single_verify_budget_us",
            "largest_signing_input_bytes",
            "maximum_observed_us",
            "deadline_detector_self_tested",
            "cases",
            "claim_boundary",
        },
        "resources.ed25519",
    )
    if (
        ed25519["schema"] != "ncp.b01-preliminary-ed25519-resource-result.v1"
        or ed25519["algorithm"] != "Ed25519"
        or ed25519["library"] != "PyNaCl"
        or ed25519["preliminary_single_verify_budget_us"] != 100_000
        or ed25519["largest_signing_input_bytes"] != 1_420_000
        or ed25519["deadline_detector_self_tested"] is not True
        or not isinstance(ed25519["pynacl_version"], str)
        or not ed25519["pynacl_version"]
        or not isinstance(ed25519["python"], str)
        or not isinstance(ed25519["platform"], str)
        or not isinstance(ed25519["claim_boundary"], str)
        or "not a production deadline" not in ed25519["claim_boundary"]
    ):
        raise ResultError("Ed25519 local-screen identity drifted")
    maximum = _nonnegative_int(
        ed25519["maximum_observed_us"], "Ed25519 maximum observed time"
    )
    if maximum > ed25519["preliminary_single_verify_budget_us"]:
        raise ResultError("Ed25519 local screen exceeded its declared budget")
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
            {"case", "message_bytes", "valid", "invalid_full_length"},
            f"resources.ed25519.cases[{index}]",
        )
        label, message_bytes, iterations = expected
        if case["case"] != label or case["message_bytes"] != message_bytes:
            raise ResultError(f"Ed25519 case identity drifted for {label}")
        _verify_timing(
            case["valid"],
            f"resources.ed25519.cases[{index}].valid",
            unit_suffix="us",
        )
        _verify_timing(
            case["invalid_full_length"],
            f"resources.ed25519.cases[{index}].invalid_full_length",
            unit_suffix="us",
        )
        if (
            case["valid"]["iterations"] != iterations
            or case["invalid_full_length"]["iterations"] != iterations
            or case["valid"]["maximum_us"]
            > ed25519["preliminary_single_verify_budget_us"]
            or case["invalid_full_length"]["maximum_us"]
            > ed25519["preliminary_single_verify_budget_us"]
        ):
            raise ResultError(f"Ed25519 case timing drifted for {label}")


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
            "model",
            "smt",
            "resources",
            "claim_boundary",
        },
        "result",
    )
    if (
        value.get("schema") != "ncp.b01-preliminary-architecture-evidence.v1"
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
    if claims.get("strongest_local_statement") != STRONGEST_LOCAL_STATEMENT:
        raise ResultError("strongest local statement drifted")


def _self_test(value: dict[str, Any]) -> None:
    mutations = (
        ("release claim", ("claim_boundary", "release_authorized"), True),
        ("contract digest", ("normative_contract_sha256",), "0" * 64),
        ("contract manifest", ("contract_manifest_sha256",), "0" * 64),
        ("source digest", ("sources", 0, "sha256"), "0" * 64),
        ("repository clean", ("repository_clean",), False),
        ("stale timestamp", ("generated_at_utc",), "1970-01-01T00:00:00Z"),
        ("model claim", ("model", "claim_boundary"), "release proven"),
        ("model survivor", ("model", "counts", "mutations_survived"), 1),
        ("SMT survivor", ("smt", "counts", "mutations_survived"), 1),
        (
            "queue detector",
            ("resources", "queue_isolation", "shared_budget_mutation_detected"),
            False,
        ),
    )
    for label, path, replacement in mutations:
        hostile = copy.deepcopy(value)
        cursor: Any = hostile
        for member in path[:-1]:
            cursor = cursor[member]
        cursor[path[-1]] = replacement
        try:
            verify(hostile)
        except ResultError:
            continue
        raise ResultError(f"self-test accepted hostile mutation: {label}")

    hostile = copy.deepcopy(value)
    hostile["model"]["optimistic_extra_claim"] = "release proven"
    try:
        verify(hostile)
    except ResultError:
        return
    raise ResultError("self-test accepted an unknown nested claim")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    value = _load()
    verify(value)
    if args.self_test:
        _self_test(value)
    canonical = json.dumps(value, separators=(",", ":"), sort_keys=True)
    print(PREFIX + canonical)
    print(
        "OK B01 preliminary evidence: "
        f"{value['model']['composition']['states']} composition states, "
        f"{value['model']['counts']['mutations_killed']} model mutations, "
        f"{value['smt']['counts']['checks']} SMT checks, "
        f"{value['smt']['counts']['mutations_killed']} SMT mutations; "
        "PROPOSED only, no independent or release claim"
        + (", verifier hostile mutations rejected" if args.self_test else "")
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, TypeError, ValueError, ResultError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
