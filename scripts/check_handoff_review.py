#!/usr/bin/env python3
"""Validate the non-normative standalone-handoff task review ledger.

The review ledger is reviewer-commentable evidence bookkeeping.  It is not a
normative protocol source and cannot authorize a release.  This checker binds its
task index to the supplied handoff ledger without requiring that out-of-repository
source file to exist in a clean checkout.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "docs" / "handoff" / "task-review.v1.json"
AUDIT_INPUTS = ROOT / "docs" / "handoff" / "audit-inputs.json"

EXPECTED_AUTHOR = "Sepehr Mahmoudian"
EXPECTED_SOURCE_NAME = "NCP_V1_0_AGENT_TASK_LEDGER.yaml"
EXPECTED_SOURCE_SCHEMA = "1.0.0"
EXPECTED_SOURCE_SHA256 = (
    "ba88fe5adae8157d16832a42833c14c73b23fbd6407118b6b999aeae88501aa3"
)
EXPECTED_TASK_INDEX_SHA256 = (
    "8106226fbd03446394531a845eefc620f4d122befe0898acf010f69d48590861"
)
EXPECTED_REVIEW_CONTENT_SHA256 = (
    "0fb76de9e074b7be4d5dde3733deca62835080b70d5df0be8b8468b030c08098"
)
EXPECTED_AUDIT_INPUTS_SHA256 = (
    "255f17b6802abe0ea5cce48edd2201594d5ea968478fc9829a0a1ae525522e68"
)
EXPECTED_TASK_COUNT = 120

TASK_ID = re.compile(r"^T[0-9]{3}$")
TASK_STATES = {"OPEN", "BLOCKED", "NOT_RUN", "NOT_CLAIMED", "COMPLETE"}
IMPLEMENTATION_COVERAGE = {
    "NONE",
    "MINIMAL",
    "PARTIAL",
    "SUBSTANTIAL",
    "COMPLETE",
    "NOT_ASSESSED",
}
TEN_LENSES = (
    "Correctness and invariants",
    "Safety and failure behavior",
    "Security and adversarial behavior",
    "Determinism and reproducibility",
    "Performance and bounded resources",
    "API, schema, and compatibility",
    "Observability and provenance",
    "Testing and independent evidence",
    "Documentation and operator usability",
    "Ecosystem composition and governance",
)
DISPOSITIONS = {
    "requested_0_9_release": "REQUIRES_NORMATIVE_REBASELINE",
    "doi_and_zenodo": "DEFERRED_NOT_ASSIGNED",
    "historical_tag_cleanup": "DECLINED_PRESERVE_IMMUTABLE_HISTORY",
}


class ReviewError(ValueError):
    """The handoff review is malformed or overclaims its evidence."""


def validate_audit_inputs() -> None:
    try:
        payload = AUDIT_INPUTS.read_bytes()
    except OSError as error:
        raise ReviewError(f"cannot read handoff audit inputs: {error}") from error
    if hashlib.sha256(payload).hexdigest() != EXPECTED_AUDIT_INPUTS_SHA256:
        raise ReviewError("handoff audit-inputs.json differs from the frozen source cut")


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, member in pairs:
        if key in value:
            raise ReviewError(f"duplicate JSON key {key!r}")
        value[key] = member
    return value


def load(path: Path = REVIEW) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_object_no_duplicates
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReviewError(f"cannot read handoff review: {error}") from error
    if not isinstance(value, dict):
        raise ReviewError("handoff review must be one JSON object")
    return value


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewError(f"{path} must be a non-empty string")
    return value


def _string_array(value: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        raise ReviewError(f"{path} must be an array")
    result = [_nonempty_string(member, f"{path}[{index}]") for index, member in enumerate(value)]
    if len(result) != len(set(result)):
        raise ReviewError(f"{path} contains a duplicate")
    return result


def _task_index(tasks: list[dict[str, Any]]) -> str:
    index = [
        {
            "id": task["id"],
            "phase": task["phase"],
            "phase_title": task["phase_title"],
            "title": task["title"],
            "dependencies": task["dependencies"],
        }
        for task in tasks
    ]
    canonical = json.dumps(
        index, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _review_content_hash(value: dict[str, Any]) -> str:
    frozen = copy.deepcopy(value)
    for task in frozen.get("tasks", []):
        if isinstance(task, dict):
            task.pop("reviewer_comment", None)
    canonical = json.dumps(
        frozen, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _validate_evidence_path(value: str, path: str) -> None:
    candidate = Path(value)
    if candidate.is_absolute():
        raise ReviewError(f"{path} must be repository-relative")
    root = ROOT.resolve()
    resolved = (ROOT / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ReviewError(f"{path} escapes the repository") from error
    if not resolved.exists():
        raise ReviewError(f"{path} does not exist in the reviewed repository")


def _validate_source(value: Any) -> None:
    if not isinstance(value, dict):
        raise ReviewError("source_ledger must be an object")
    expected = {
        "name": EXPECTED_SOURCE_NAME,
        "handoff_schema": EXPECTED_SOURCE_SCHEMA,
        "sha256": EXPECTED_SOURCE_SHA256,
        "task_count": EXPECTED_TASK_COUNT,
        "task_index_sha256": EXPECTED_TASK_INDEX_SHA256,
    }
    if value != expected:
        raise ReviewError("source_ledger does not match the reviewed handoff source identity")


def _validate_global_findings(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"ten_lenses"}:
        raise ReviewError("global_findings must contain exactly ten_lenses")
    findings = value["ten_lenses"]
    if not isinstance(findings, list) or len(findings) != len(TEN_LENSES):
        raise ReviewError("global_findings.ten_lenses must contain exactly ten findings")
    names: list[str] = []
    for index, finding in enumerate(findings):
        path = f"global_findings.ten_lenses[{index}]"
        if not isinstance(finding, dict) or set(finding) != {
            "lens",
            "finding",
            "residual_risk",
        }:
            raise ReviewError(f"{path} has an unexpected shape")
        names.append(_nonempty_string(finding["lens"], f"{path}.lens"))
        _nonempty_string(finding["finding"], f"{path}.finding")
        _nonempty_string(finding["residual_risk"], f"{path}.residual_risk")
    if tuple(names) != TEN_LENSES:
        raise ReviewError("global ten-lens findings are missing, reordered, or renamed")


def _validate_dispositions(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != set(DISPOSITIONS):
        raise ReviewError("requested_dispositions must contain the three reviewed requests")
    for name, expected in DISPOSITIONS.items():
        entry = value[name]
        path = f"requested_dispositions.{name}"
        if not isinstance(entry, dict) or set(entry) != {
            "disposition",
            "action_taken",
            "finding",
        }:
            raise ReviewError(f"{path} has an unexpected shape")
        if entry["disposition"] != expected:
            raise ReviewError(f"{path}.disposition must be {expected}")
        if entry["action_taken"] is not False:
            raise ReviewError(f"{path}.action_taken must remain false")
        _nonempty_string(entry["finding"], f"{path}.finding")


def _validate_task(task: Any, index: int, earlier: set[str]) -> dict[str, Any]:
    path = f"tasks[{index}]"
    expected_fields = {
        "id",
        "phase",
        "phase_title",
        "title",
        "dependencies",
        "state",
        "implementation_coverage",
        "evidence_summary",
        "gap_summary",
        "evidence",
        "residual_risk",
        "reviewer_comment",
    }
    if not isinstance(task, dict) or set(task) != expected_fields:
        raise ReviewError(f"{path} has an unexpected shape")

    identifier = _nonempty_string(task["id"], f"{path}.id")
    if TASK_ID.fullmatch(identifier) is None:
        raise ReviewError(f"{path}.id is not canonical")
    if task["phase"] not in range(1, 13):
        raise ReviewError(f"{path}.phase must be an integer from 1 through 12")
    _nonempty_string(task["phase_title"], f"{path}.phase_title")
    _nonempty_string(task["title"], f"{path}.title")

    dependencies = _string_array(task["dependencies"], f"{path}.dependencies")
    for dependency in dependencies:
        if dependency not in earlier:
            raise ReviewError(
                f"{path}.dependencies references non-earlier task {dependency!r}"
            )

    state = task["state"]
    coverage = task["implementation_coverage"]
    if state not in TASK_STATES:
        raise ReviewError(f"{path}.state must be one of {sorted(TASK_STATES)}")
    if coverage not in IMPLEMENTATION_COVERAGE:
        raise ReviewError(
            f"{path}.implementation_coverage must be one of "
            f"{sorted(IMPLEMENTATION_COVERAGE)}"
        )

    evidence_summary = _nonempty_string(task["evidence_summary"], f"{path}.evidence_summary")
    gap_summary = _nonempty_string(task["gap_summary"], f"{path}.gap_summary")
    residual_risk = _nonempty_string(task["residual_risk"], f"{path}.residual_risk")
    evidence = task["evidence"]
    if not isinstance(evidence, dict) or set(evidence) != {"paths", "commands"}:
        raise ReviewError(f"{path}.evidence must contain exactly paths and commands")
    evidence_paths = _string_array(evidence["paths"], f"{path}.evidence.paths")
    evidence_commands = _string_array(evidence["commands"], f"{path}.evidence.commands")
    for evidence_index, evidence_path in enumerate(evidence_paths):
        _validate_evidence_path(
            evidence_path, f"{path}.evidence.paths[{evidence_index}]"
        )

    comment = task["reviewer_comment"]
    if comment is not None:
        _nonempty_string(comment, f"{path}.reviewer_comment")

    if state != "OPEN":
        raise ReviewError(f"{path}.state must remain OPEN in this comment-only review")

    combined = " ".join((evidence_summary, gap_summary, residual_risk)).upper()
    if state == "COMPLETE":
        if coverage != "COMPLETE":
            raise ReviewError(f"{path}: COMPLETE requires COMPLETE implementation coverage")
        if not evidence_paths or not evidence_commands:
            raise ReviewError(f"{path}: COMPLETE requires retained paths and commands")
        if "NOT RUN" in combined or "NOT_RUN" in combined:
            raise ReviewError(f"{path}: COMPLETE cannot retain a NOT RUN acceptance gap")
    elif coverage == "COMPLETE":
        raise ReviewError(f"{path}: COMPLETE coverage cannot accompany state {state}")

    if state == "NOT_RUN":
        if coverage not in {"NONE", "NOT_ASSESSED"}:
            raise ReviewError(f"{path}: NOT_RUN cannot claim implemented coverage")
        if evidence_commands:
            raise ReviewError(f"{path}: NOT_RUN cannot claim executed evidence commands")
        if "NOT RUN" not in combined and "NOT_RUN" not in combined:
            raise ReviewError(f"{path}: NOT_RUN must be explicit in the review text")

    return task


def validate(value: dict[str, Any]) -> None:
    expected_top_level = {
        "schema",
        "normative",
        "review_status",
        "author",
        "release_authorized",
        "claim_boundary",
        "source_ledger",
        "review_basis",
        "implementation_coverage_scale",
        "global_findings",
        "requested_dispositions",
        "tasks",
    }
    if set(value) != expected_top_level:
        raise ReviewError("handoff review has an unexpected top-level shape")
    if value.get("schema") != "ncp.handoff-task-review.v1":
        raise ReviewError("schema must be ncp.handoff-task-review.v1")
    if value.get("normative") is not False:
        raise ReviewError("the handoff review must remain non-normative")
    if value.get("review_status") != "OPEN_FOR_REVIEWER_REVIEW":
        raise ReviewError("review_status must remain OPEN_FOR_REVIEWER_REVIEW")
    if value.get("author") != {"name": EXPECTED_AUTHOR}:
        raise ReviewError(f"author must be {EXPECTED_AUTHOR}")
    if value.get("release_authorized") is not False:
        raise ReviewError("a handoff review cannot authorize release")
    _nonempty_string(value.get("claim_boundary"), "claim_boundary")
    _validate_source(value.get("source_ledger"))
    review_basis = value.get("review_basis")
    if not isinstance(review_basis, dict) or set(review_basis) != {
        "initial_source_commit",
        "repository_candidate",
        "wire_version",
        "compact_contract_hash",
        "worktree_note",
    }:
        raise ReviewError("review_basis has an unexpected shape")
    if review_basis["initial_source_commit"] != "2527b36a9d187d2bdee19ccf471b1efbdeed2fab":
        raise ReviewError("review_basis initial source commit changed")
    if review_basis["repository_candidate"] != "1.0.0-rc.1":
        raise ReviewError("review_basis candidate changed")
    if review_basis["wire_version"] != "1.0":
        raise ReviewError("review_basis wire version changed")
    if review_basis["compact_contract_hash"] != "163acc57d8a62b66":
        raise ReviewError("review_basis compact contract hash changed")
    _nonempty_string(review_basis["worktree_note"], "review_basis.worktree_note")
    scale = value.get("implementation_coverage_scale")
    if not isinstance(scale, dict) or set(scale) != IMPLEMENTATION_COVERAGE:
        raise ReviewError("implementation_coverage_scale is incomplete or extended")
    for name, description in scale.items():
        _nonempty_string(description, f"implementation_coverage_scale.{name}")
    _validate_global_findings(value.get("global_findings"))
    _validate_dispositions(value.get("requested_dispositions"))

    tasks = value.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != EXPECTED_TASK_COUNT:
        raise ReviewError(f"tasks must contain exactly {EXPECTED_TASK_COUNT} entries")
    expected_ids = [f"T{index:03d}" for index in range(EXPECTED_TASK_COUNT)]
    actual_ids: list[str] = []
    titles: list[str] = []
    earlier: set[str] = set()
    checked: list[dict[str, Any]] = []
    for index, task in enumerate(tasks):
        checked_task = _validate_task(task, index, earlier)
        identifier = checked_task["id"]
        actual_ids.append(identifier)
        titles.append(checked_task["title"])
        earlier.add(identifier)
        checked.append(checked_task)
    if actual_ids != expected_ids:
        raise ReviewError("task IDs must be the exact contiguous ordered range T000 through T119")
    if len(titles) != len(set(titles)):
        raise ReviewError("task titles must be unique")
    if _task_index(checked) != EXPECTED_TASK_INDEX_SHA256:
        raise ReviewError(
            "task IDs, titles, phases, phase titles, or dependencies differ from the source ledger"
        )
    if _review_content_hash(value) != EXPECTED_REVIEW_CONTENT_SHA256:
        raise ReviewError(
            "review content changed outside reviewer_comment; update requires a reviewed guard change"
        )


def self_test(good: dict[str, Any]) -> None:
    validate(good)
    comment_only = copy.deepcopy(good)
    comment_only["tasks"][0]["reviewer_comment"] = "Review this evidence."
    validate(comment_only)

    bad_author = copy.deepcopy(good)
    bad_author["author"]["name"] = "Someone Else"
    closed_task = copy.deepcopy(good)
    closed_task["tasks"][0]["state"] = "COMPLETE"
    closed_task["tasks"][0]["implementation_coverage"] = "COMPLETE"
    missing_path = copy.deepcopy(good)
    missing_path["tasks"][0]["evidence"]["paths"] = ["does/not/exist"]
    false_command = copy.deepcopy(good)
    false_command["tasks"][0]["evidence"]["commands"] = ["false"]
    changed_gap = copy.deepcopy(good)
    changed_gap["tasks"][0]["gap_summary"] = "Acceptance waived."
    changed_source = copy.deepcopy(good)
    changed_source["source_ledger"]["sha256"] = "0" * 64
    hostile = (
        bad_author,
        closed_task,
        missing_path,
        false_command,
        changed_gap,
        changed_source,
    )
    for mutation in hostile:
        try:
            validate(mutation)
        except ReviewError:
            continue
        raise AssertionError("hostile handoff-review mutation passed validation")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        validate_audit_inputs()
        value = load()
        validate(value)
        if args.self_test:
            self_test(value)
    except (ReviewError, AssertionError) as error:
        print(f"HANDOFF REVIEW FAILURE: {error}", file=sys.stderr)
        return 1
    print(
        "OK handoff review: 120 exact source tasks remain non-normative and "
        "reviewer-commentable; non-comment content frozen"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
