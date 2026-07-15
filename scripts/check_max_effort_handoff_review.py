#!/usr/bin/env python3
"""Validate the non-normative max-effort handoff review ledger.

The guard freezes the exact external source index, audit inputs, task/lens set,
NO_GO boundary, and every non-comment review field.  A reviewer may change only
``reviewer_comment`` values to non-empty strings.  Comments cannot close a task,
resolve a lens, waive evidence, authorize a release, or change source identity.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs" / "handoff" / "max-effort-source-index.v2.json"
AUDIT = ROOT / "docs" / "handoff" / "max-effort-audit-inputs.v2.json"
REVIEW = ROOT / "docs" / "handoff" / "max-effort-task-review.v2.json"
FILE_LEDGER = ROOT / "docs" / "handoff" / "max-effort-file-review.v2.csv"
FILE_MANIFEST = ROOT / "docs" / "handoff" / "max-effort-file-review-manifest.v2.json"

EXPECTED_AUTHOR = "Sepehr Mahmoudian"
EXPECTED_INDEX_SHA256 = (
    "2e0337544d91a780415d5f86e6372f2067121fc60244c8a30d5231e5ab031b51"
)
EXPECTED_AUDIT_SHA256 = (
    "7932dbcfeac3014efc5f0977403c4e4df89a0072b03e2f1d4f6326f224b218eb"
)
EXPECTED_REVIEW_CONTENT_SHA256 = (
    "da0218dd783b24f12fda2a5204fc5a23fddd8c1b82185ddf18ceef9a59b2ef5b"
)
EXPECTED_CANONICAL_INDEX_SHA256 = (
    "b4290ad1b08be16e1400c008d642ee14b416d6f39a33bb65c44f53dccd09897f"
)
EXPECTED_LEDGER_SHA256 = (
    "9a411e41f1e44324311316af20404632b085b167e70eff1914aaff02ce65e947"
)
FROZEN_COMMIT = "0ba5ff6e963225b0635f8fec349278f1ac287df3"
REVIEWED_COMMIT = "f08c2ad5f68bab0a583db918439660636996ca07"
LENS_IDS = tuple(f"L{number:02d}" for number in range(1, 21))
TASK_IDS = tuple(f"T{number:03d}" for number in range(146))
TASK_ID = re.compile(r"^T[0-9]{3}$")
COVERAGE = {"NONE", "MINIMAL", "PARTIAL", "SUBSTANTIAL", "NOT_ASSESSED"}
EXTERNAL_GATES = (
    "live-mtls-acl-rotation-revocation",
    "two-independent-non-rust-live-peers",
    "fault-backpressure-restart-soak",
    "fuzz-sanitizer-duration",
    "performance-resource-profile",
    "installed-package-matrix",
    "registry-namespace-ownership",
    "consumer-certification",
    "independent-clean-room-reproduction",
    "signed-sbom-provenance",
)


class ReviewError(ValueError):
    """The max-effort review is malformed or overclaims its evidence."""


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, member in pairs:
        if key in value:
            raise ReviewError(f"duplicate JSON key {key!r}")
        value[key] = member
    return value


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_object_no_duplicates
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReviewError(f"cannot read {path.name}: {error}") from error
    if not isinstance(value, dict):
        raise ReviewError(f"{path.name} must contain one JSON object")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ReviewError(f"cannot hash {path}: {error}") from error


def _git(*args: str) -> bytes:
    environment = os.environ.copy()
    environment.pop("GIT_EXTERNAL_DIFF", None)
    environment.pop("GIT_DIFF_OPTS", None)
    environment["LC_ALL"] = "C"
    try:
        return subprocess.check_output(
            [
                "git",
                "--no-pager",
                "-c",
                "color.ui=false",
                "-c",
                "core.quotePath=true",
                "-C",
                str(ROOT),
                *args,
            ],
            stderr=subprocess.PIPE,
            env=environment,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ReviewError(f"git {' '.join(args)} failed: {error}") from error


def _git_json(path: str) -> dict[str, Any]:
    try:
        value = json.loads(
            _git("show", f"{REVIEWED_COMMIT}:{path}"),
            object_pairs_hook=_object_no_duplicates,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ReviewError(f"cannot parse {path} at reviewed source: {error}") from error
    if not isinstance(value, dict):
        raise ReviewError(f"{path} at reviewed source must contain one JSON object")
    return value


def _nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewError(f"{path} must be a non-empty string")
    return value


def _strings(value: Any, path: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        qualifier = "an array" if allow_empty else "a non-empty array"
        raise ReviewError(f"{path} must be {qualifier}")
    result = [
        _nonempty(member, f"{path}[{index}]") for index, member in enumerate(value)
    ]
    if len(result) != len(set(result)):
        raise ReviewError(f"{path} contains a duplicate")
    return result


def _canonical_index(value: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"twenty_lenses": value["twenty_lenses"], "tasks": value["tasks"]},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _review_content(value: dict[str, Any]) -> str:
    frozen = copy.deepcopy(value)
    for task in frozen.get("tasks", []):
        if isinstance(task, dict):
            task.pop("reviewer_comment", None)
    canonical = json.dumps(
        frozen, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_index(value: dict[str, Any]) -> None:
    if set(value) != {"schema", "normative", "source", "twenty_lenses", "tasks"}:
        raise ReviewError("source index has an unexpected top-level shape")
    if value["schema"] != "ncp.max-effort-handoff-source-index.v2":
        raise ReviewError("source index schema is wrong")
    if value["normative"] is not False:
        raise ReviewError("source index must remain non-normative")
    expected_source = {
        "file_name": "MASTER_TASK_LEDGER.yaml",
        "handoff_schema": "2.0.0",
        "sha256": EXPECTED_LEDGER_SHA256,
        "project": "NCP",
        "repository": "https://github.com/sepahead/NCP",
        "frozen_commit": FROZEN_COMMIT,
        "release_target": "1.0.0",
    }
    if value["source"] != expected_source:
        raise ReviewError("source index does not match the external ledger identity")

    lenses = value["twenty_lenses"]
    if not isinstance(lenses, list) or len(lenses) != 20:
        raise ReviewError("source index must contain exactly twenty lenses")
    lens_ids: list[str] = []
    for number, lens in enumerate(lenses):
        path = f"twenty_lenses[{number}]"
        if not isinstance(lens, dict) or set(lens) != {"id", "name", "question"}:
            raise ReviewError(f"{path} has an unexpected shape")
        lens_ids.append(_nonempty(lens["id"], f"{path}.id"))
        _nonempty(lens["name"], f"{path}.name")
        _nonempty(lens["question"], f"{path}.question")
    if tuple(lens_ids) != LENS_IDS:
        raise ReviewError("source lens IDs must be the exact ordered L01 through L20")

    tasks = value["tasks"]
    if not isinstance(tasks, list) or len(tasks) != 146:
        raise ReviewError("source index must contain exactly 146 tasks")
    task_ids: list[str] = []
    expected_fields = {
        "id",
        "phase",
        "title",
        "source_scope",
        "focus",
        "dependencies",
        "execution_wave",
        "subagent_lane",
    }
    for number, task in enumerate(tasks):
        path = f"tasks[{number}]"
        if not isinstance(task, dict) or set(task) != expected_fields:
            raise ReviewError(f"{path} has an unexpected source-index shape")
        identifier = _nonempty(task["id"], f"{path}.id")
        if TASK_ID.fullmatch(identifier) is None:
            raise ReviewError(f"{path}.id is not canonical")
        task_ids.append(identifier)
        for field in ("phase", "title", "source_scope", "focus"):
            _nonempty(task[field], f"{path}.{field}")
        dependencies = _strings(
            task["dependencies"], f"{path}.dependencies", allow_empty=True
        )
        expected_dependencies = [] if number == 0 else [TASK_IDS[number - 1]]
        if dependencies != expected_dependencies:
            raise ReviewError(
                f"{path}.dependencies must preserve the handoff's strict predecessor chain"
            )
        if (
            not isinstance(task["execution_wave"], int)
            or isinstance(task["execution_wave"], bool)
            or task["execution_wave"] not in range(10)
        ):
            raise ReviewError(
                f"{path}.execution_wave must be an integer from 0 through 9"
            )
        if (
            not isinstance(task["subagent_lane"], int)
            or isinstance(task["subagent_lane"], bool)
            or task["subagent_lane"] not in range(1, 4)
        ):
            raise ReviewError(
                f"{path}.subagent_lane must be an integer from 1 through 3"
            )
    if tuple(task_ids) != TASK_IDS:
        raise ReviewError("source task IDs must be the exact ordered T000 through T145")
    if _canonical_index(value) != EXPECTED_CANONICAL_INDEX_SHA256:
        raise ReviewError("canonical task/lens index differs from the reviewed ledger")


def validate_audit(value: dict[str, Any]) -> None:
    required = {
        "schema",
        "normative",
        "author",
        "captured_at_utc",
        "claim_boundary",
        "scope",
        "handoff_package",
        "source_cuts",
        "reviewed_source_inventory",
        "locked_inputs",
        "normative_identities",
        "local_environment",
        "handoff_defects",
        "known_external_gates",
        "cross_repository_boundary",
        "history_inventory",
    }
    if set(value) != required:
        raise ReviewError("audit inputs have an unexpected top-level shape")
    if value["schema"] != "ncp.max-effort-handoff-audit-inputs.v2":
        raise ReviewError("audit schema is wrong")
    if value["normative"] is not False:
        raise ReviewError("audit inputs must remain non-normative")
    author = value["author"]
    if not isinstance(author, dict) or author.get("name") != EXPECTED_AUTHOR:
        raise ReviewError("audit author must remain Sepehr Mahmoudian")
    _nonempty(value["captured_at_utc"], "captured_at_utc")
    _nonempty(value["claim_boundary"], "claim_boundary")

    scope = value["scope"]
    if not isinstance(scope, dict):
        raise ReviewError("scope must be an object")
    expected_scope = {
        "handoff_target": "1.0.0",
        "repository_candidate": "1.0.0-rc.1",
        "wire_version": "1.0",
        "compact_contract_hash": "163acc57d8a62b66",
        "release_allowed": False,
        "decision": "NO_GO",
        "requested_0_9_disposition": "REQUIRES_CROSS_REPOSITORY_NORMATIVE_REBASELINE",
        "doi": "NOT_ASSIGNED",
        "zenodo_archive": "NOT_CREATED",
    }
    if scope != expected_scope:
        raise ReviewError("audit scope/version/release boundary has drifted")

    package = value["handoff_package"]
    if not isinstance(package, dict):
        raise ReviewError("handoff_package must be an object")
    artifacts = package.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 22:
        raise ReviewError("handoff package must bind exactly 22 child artifacts")
    paths: list[str] = []
    for number, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            raise ReviewError(f"handoff artifact {number} has an unexpected shape")
        paths.append(_nonempty(artifact["path"], f"handoff artifact {number}.path"))
        digest = _nonempty(artifact["sha256"], f"handoff artifact {number}.sha256")
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ReviewError(
                f"handoff artifact {number}.sha256 is not lowercase SHA-256"
            )
    if len(paths) != len(set(paths)):
        raise ReviewError("handoff package contains duplicate artifact paths")

    cuts = value["source_cuts"]
    try:
        frozen = cuts["handoff_frozen"]
        reviewed = cuts["reviewed_current"]
        intervening = cuts["intervening_diff"]
    except (TypeError, KeyError) as error:
        raise ReviewError("source_cuts are incomplete") from error
    if frozen.get("commit") != FROZEN_COMMIT:
        raise ReviewError("handoff frozen source commit drifted")
    if reviewed.get("commit") != REVIEWED_COMMIT:
        raise ReviewError("reviewed source commit drifted")
    if reviewed.get("origin_main_at_capture") != REVIEWED_COMMIT:
        raise ReviewError("reviewed source was not bound to origin/main at capture")
    if reviewed.get("worktree_was_clean_at_capture") is not True:
        raise ReviewError("reviewed source cut must record a clean worktree")
    if reviewed.get("status") != "LOCAL_REVIEW_CUT_NOT_RELEASE_AUTHORIZATION":
        raise ReviewError("reviewed source cut must retain its non-release boundary")
    hosted = reviewed.get("hosted_ci")
    if (
        not isinstance(hosted, dict)
        or hosted.get("head_sha") != REVIEWED_COMMIT
        or hosted.get("conclusion") != "success"
    ):
        raise ReviewError(
            "reviewed source cut must retain its successful exact-SHA CI receipt"
        )
    if intervening.get("range") != f"{FROZEN_COMMIT}..{REVIEWED_COMMIT}":
        raise ReviewError("intervening diff range drifted")
    if [
        intervening.get(key) for key in ("changed_files", "insertions", "deletions")
    ] != [174, 35924, 13418]:
        raise ReviewError("intervening diff statistics drifted")

    inventory = value["reviewed_source_inventory"]
    if (
        not isinstance(inventory, dict)
        or inventory.get("source_commit") != REVIEWED_COMMIT
    ):
        raise ReviewError("file inventory is not bound to the reviewed source cut")
    if [
        inventory.get(key) for key in ("tracked_files", "tracked_bytes", "text_lines")
    ] != [793, 7817402, 191813]:
        raise ReviewError("reviewed source inventory counts drifted")
    if inventory.get("review_status") not in {
        "THREE_LANE_REVIEW_IN_PROGRESS",
        "THREE_LANE_REVIEW_COMPLETE_WITH_OPEN_FINDINGS",
        "THREE_LANE_INTERNAL_AI_REVIEW_COMPLETE_WITH_OPEN_FINDINGS",
    }:
        raise ReviewError("reviewed source inventory has an invalid status")
    _nonempty(inventory.get("limitation"), "reviewed_source_inventory.limitation")

    identities = value["normative_identities"]
    expected_identities = {
        "complete_contract_sha256": "9cae331742d01e9b164e029aa06c644e6b1886176d0816a6ef883af138355c90",
        "mandatory_corpus_sha256": "83bdcfae2e07f1c69efa87279f0b3c27392be83f31b292647cddd10eb35226b3",
        "compact_proto_fnv1a64": "163acc57d8a62b66",
        "required_vectors": 282,
        "stable_vectors": 275,
        "migration_vectors": 7,
    }
    if identities != expected_identities:
        raise ReviewError("normative identity or 282-vector inventory drifted")
    defects = _strings(value["handoff_defects"], "handoff_defects")
    if len(defects) != 9:
        raise ReviewError("audit must retain all nine handoff defects")
    gates = value["known_external_gates"]
    if not isinstance(gates, dict) or gates.get("status") != "NOT_RUN":
        raise ReviewError("external gates must remain NOT_RUN")
    if tuple(gates.get("ids", [])) != EXTERNAL_GATES:
        raise ReviewError("external gate set drifted")
    boundary = value["cross_repository_boundary"]
    if (
        not isinstance(boundary, dict)
        or boundary.get("mutations_performed") is not False
        or boundary.get("ncp_wire_1_0_consumers_certified") != 0
    ):
        raise ReviewError(
            "cross-repository boundary overclaims mutation or certification"
        )
    history = value["history_inventory"]
    if (
        not isinstance(history, dict)
        or history.get("latest_immutable_release") != "v0.8.0"
        or history.get("destructive_cleanup_disposition")
        != "RETAIN_IMMUTABLE_COMPATIBILITY_AND_MIGRATION_EVIDENCE"
    ):
        raise ReviewError("immutable history disposition drifted")


def validate_repository_evidence(value: dict[str, Any]) -> None:
    """Recompute repository-owned audit facts instead of trusting prose alone."""
    cuts = value["source_cuts"]
    frozen = cuts["handoff_frozen"]
    reviewed = cuts["reviewed_current"]
    intervening = cuts["intervening_diff"]

    _git("merge-base", "--is-ancestor", FROZEN_COMMIT, REVIEWED_COMMIT)
    _git("merge-base", "--is-ancestor", REVIEWED_COMMIT, "HEAD")

    reviewed_tree = _git("rev-parse", f"{REVIEWED_COMMIT}^{{tree}}").decode().strip()
    frozen_tree = _git("rev-parse", f"{FROZEN_COMMIT}^{{tree}}").decode().strip()
    authored_at = _git("show", "-s", "--format=%aI", REVIEWED_COMMIT).decode().strip()
    if reviewed.get("tree") != reviewed_tree or frozen.get("tree") != frozen_tree:
        raise ReviewError("source-cut tree identity does not match Git objects")
    if reviewed.get("authored_at") != authored_at:
        raise ReviewError("reviewed source author timestamp does not match Git")

    expected_hosted = {
        "provider": "GitHub Actions",
        "run_id": 29366777050,
        "url": "https://github.com/sepahead/NCP/actions/runs/29366777050",
        "head_sha": REVIEWED_COMMIT,
        "conclusion": "success",
    }
    if reviewed.get("hosted_ci") != expected_hosted:
        raise ReviewError("hosted CI receipt differs from the exact successful run")

    diff_range = f"{FROZEN_COMMIT}..{REVIEWED_COMMIT}"
    changed_paths = [
        path
        for path in _git(
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            "--name-only",
            "-z",
            diff_range,
        ).split(b"\0")
        if path
    ]
    insertions = 0
    deletions = 0
    for record in _git(
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--no-renames",
        "--numstat",
        "-z",
        diff_range,
    ).split(b"\0"):
        if not record:
            continue
        fields = record.split(b"\t", 2)
        if len(fields) != 3:
            raise ReviewError("reviewed diff emitted malformed numstat data")
        if fields[0].isdigit():
            insertions += int(fields[0])
        if fields[1].isdigit():
            deletions += int(fields[1])
    derived_diff = {
        "range": diff_range,
        "changed_files": len(changed_paths),
        "insertions": insertions,
        "deletions": deletions,
        "binary_full_index_patch_sha256": hashlib.sha256(
            _git(
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--no-renames",
                "--binary",
                "--full-index",
                "--src-prefix=a/",
                "--dst-prefix=b/",
                "--submodule=short",
                diff_range,
            )
        ).hexdigest(),
        "nul_name_status_sha256": hashlib.sha256(
            _git(
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--no-renames",
                "--name-status",
                "-z",
                diff_range,
            )
        ).hexdigest(),
        "reviewed_tree_ls_tree_sha256": hashlib.sha256(
            _git("ls-tree", "-r", "-z", "--full-tree", REVIEWED_COMMIT)
        ).hexdigest(),
    }
    if intervening != derived_diff:
        raise ReviewError("intervening diff identity does not match Git")

    inventory = value["reviewed_source_inventory"]
    manifest = load(FILE_MANIFEST)
    ledger_sha256 = _sha256(FILE_LEDGER)
    manifest_sha256 = _sha256(FILE_MANIFEST)
    reviewers = manifest.get("reviewers")
    if not isinstance(reviewers, list) or len(reviewers) != 3:
        raise ReviewError("file-review manifest must contain exactly three lanes")
    lane_files = [lane.get("files") for lane in reviewers if isinstance(lane, dict)]
    lane_lines = [
        lane.get("text_lines") for lane in reviewers if isinstance(lane, dict)
    ]
    expected_manifest = {
        "source_commit": REVIEWED_COMMIT,
        "source_tree": reviewed_tree,
        "tracked_files": inventory["tracked_files"],
        "tracked_bytes": inventory["tracked_bytes"],
        "text_lines": inventory["text_lines"],
        "internally_reviewed_files": inventory["internally_reviewed_files"],
        "independently_reviewed_files": inventory["independently_reviewed_files"],
        "review_status": "INTERNAL_AI_REVIEW_COMPLETE_WITH_OPEN_FINDINGS",
        "completed_at": inventory["internal_review_completed_at_utc"],
        "decision": "NO_GO",
        "csv_sha256": ledger_sha256,
    }
    for key, expected in expected_manifest.items():
        if manifest.get(key) != expected:
            raise ReviewError(f"file-review manifest {key} differs from its audit")
    if lane_files != inventory.get("three_lane_file_totals"):
        raise ReviewError("file-review lane file totals differ from the audit")
    if lane_lines != inventory.get("three_lane_line_totals"):
        raise ReviewError("file-review lane line totals differ from the audit")
    if inventory.get("corrected_review_csv_sha256") != ledger_sha256:
        raise ReviewError("audited file-review CSV digest does not match its bytes")
    if inventory.get("corrected_review_manifest_sha256") != manifest_sha256:
        raise ReviewError(
            "audited file-review manifest digest does not match its bytes"
        )

    locked_inputs = value["locked_inputs"]
    expected_locked_paths = {
        "Cargo.lock",
        "bun.lock",
        "contract/manifest.v1.json",
        "conformance/manifest.v1.json",
    }
    if (
        not isinstance(locked_inputs, dict)
        or set(locked_inputs) != expected_locked_paths
    ):
        raise ReviewError("locked-input set differs from the exact reviewed inputs")
    for path, expected in locked_inputs.items():
        actual = hashlib.sha256(_git("show", f"{REVIEWED_COMMIT}:{path}")).hexdigest()
        if actual != expected:
            raise ReviewError(f"locked input {path} differs from the reviewed source")

    contract = _git_json("contract/manifest.v1.json")
    conformance = _git_json("conformance/manifest.v1.json")
    release_gates = _git_json("contract/release-gates.v1.json")
    counts = conformance.get("counts")
    identities = value["normative_identities"]
    derived_identities = {
        "complete_contract_sha256": contract.get("contract_digest_sha256"),
        "mandatory_corpus_sha256": conformance.get("corpus_digest_sha256"),
        "compact_proto_fnv1a64": contract.get("wire_proto_contract_hash_fnv1a64"),
        "required_vectors": counts.get("required_total")
        if isinstance(counts, dict)
        else None,
        "stable_vectors": counts.get("stable_1_0")
        if isinstance(counts, dict)
        else None,
        "migration_vectors": counts.get("migration_only")
        if isinstance(counts, dict)
        else None,
    }
    if identities != derived_identities:
        raise ReviewError("normative identities differ from the reviewed manifests")
    if conformance.get("contract_hash") != identities["compact_proto_fnv1a64"]:
        raise ReviewError("contract compact hash differs across reviewed manifests")
    pre_release_gates = release_gates.get("pre_release_gates")
    if not isinstance(pre_release_gates, list):
        raise ReviewError("reviewed release policy has no pre-release gate array")
    derived_external_gates = tuple(
        gate.get("id")
        for gate in pre_release_gates
        if isinstance(gate, dict)
        and gate.get("required") is True
        and gate.get("local") is False
    )
    if derived_external_gates != tuple(value["known_external_gates"]["ids"]):
        raise ReviewError(
            "external gate audit differs from the reviewed release policy"
        )
    if release_gates.get("release_allowed") is not False:
        raise ReviewError("reviewed release policy no longer retains its release hold")

    generated = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_file_review_ledger.py"),
            "--source",
            REVIEWED_COMMIT,
            "--review-status",
            "INTERNAL_AI_REVIEW_COMPLETE_WITH_OPEN_FINDINGS",
            "--completed-at",
            inventory["internal_review_completed_at_utc"],
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if generated.returncode != 0:
        detail = generated.stderr.strip() or generated.stdout.strip()
        raise ReviewError(f"file-review ledger is not reproducible: {detail}")


def _validate_evidence_path(value: str, path: str, root: Path = ROOT) -> None:
    candidate = Path(value)
    if candidate.is_absolute():
        raise ReviewError(f"{path} must be repository-relative")
    if not candidate.parts or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ReviewError(f"{path} contains a forbidden path component")
    cursor = root
    for part in candidate.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ReviewError(f"{path} traverses a symlink")
    try:
        resolved_root = root.resolve(strict=True)
        resolved = (root / candidate).resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as error:
        raise ReviewError(f"{path} is missing or escapes the repository") from error
    if not resolved.is_file():
        raise ReviewError(f"{path} must identify a regular file")


def _validate_reference(value: Any, expected: dict[str, Any], path: str) -> None:
    if value != expected:
        raise ReviewError(f"{path} differs from its exact reviewed identity")


def validate_review(value: dict[str, Any], index: dict[str, Any]) -> None:
    expected_top = {
        "schema",
        "normative",
        "review_status",
        "author",
        "release_authorized",
        "claim_boundary",
        "source_index",
        "audit_inputs",
        "execution_disposition",
        "completion_summary",
        "requested_dispositions",
        "global_twenty_lens_findings",
        "tasks",
    }
    if set(value) != expected_top:
        raise ReviewError("review has an unexpected top-level shape")
    if value["schema"] != "ncp.max-effort-handoff-task-review.v2":
        raise ReviewError("review schema is wrong")
    if value["normative"] is not False:
        raise ReviewError("review must remain non-normative")
    if value["review_status"] != "NO_GO_OPEN_FOR_REVIEWER_REVIEW":
        raise ReviewError("review status must remain NO_GO and open")
    if value["author"] != {"name": EXPECTED_AUTHOR}:
        raise ReviewError("review author must remain Sepehr Mahmoudian")
    if value["release_authorized"] is not False:
        raise ReviewError("review must never authorize a release")
    _nonempty(value["claim_boundary"], "claim_boundary")

    _validate_reference(
        value["source_index"],
        {
            "path": "docs/handoff/max-effort-source-index.v2.json",
            "sha256": EXPECTED_INDEX_SHA256,
            "source_ledger": "MASTER_TASK_LEDGER.yaml",
            "source_ledger_sha256": EXPECTED_LEDGER_SHA256,
            "canonical_task_and_lens_index_sha256": EXPECTED_CANONICAL_INDEX_SHA256,
            "task_count": 146,
            "lens_count": 20,
        },
        "source_index",
    )
    _validate_reference(
        value["audit_inputs"],
        {
            "path": "docs/handoff/max-effort-audit-inputs.v2.json",
            "sha256": EXPECTED_AUDIT_SHA256,
            "reviewed_source_commit": REVIEWED_COMMIT,
            "handoff_frozen_commit": FROZEN_COMMIT,
        },
        "audit_inputs",
    )
    expected_execution = {
        "declared_waves": 10,
        "declared_lanes": 3,
        "dependency_graph": "STRICT_SINGLE_CHAIN_T000_THROUGH_T145",
        "legal_task_execution": "SERIAL_AS_WRITTEN",
        "parallel_activity_boundary": "Independent file inspection may run in parallel, but it cannot close dependent tasks out of order.",
    }
    if value["execution_disposition"] != expected_execution:
        raise ReviewError(
            "execution disposition no longer records the handoff DAG conflict"
        )
    expected_summary = {
        "tasks_total": 146,
        "tasks_complete": 0,
        "tasks_open": 146,
        "lens_reviews_total": 2920,
        "lens_reviews_resolved": 0,
        "lens_reviews_open": 2920,
        "decision": "NO_GO",
    }
    if value["completion_summary"] != expected_summary:
        raise ReviewError("completion summary must remain 146 OPEN / 2920 OPEN / NO_GO")

    dispositions = value["requested_dispositions"]
    expected_dispositions = {
        "requested_0_9_release": "REQUIRES_CROSS_REPOSITORY_NORMATIVE_REBASELINE",
        "doi_and_zenodo": "DEFERRED_NOT_ASSIGNED",
        "historical_tag_and_release_cleanup": "RETAIN_IMMUTABLE_HISTORY",
    }
    if not isinstance(dispositions, dict) or set(dispositions) != set(
        expected_dispositions
    ):
        raise ReviewError("requested dispositions have an unexpected shape")
    for name, expected in expected_dispositions.items():
        entry = dispositions[name]
        if not isinstance(entry, dict) or set(entry) != {
            "disposition",
            "action_taken",
            "finding",
        }:
            raise ReviewError(f"requested_dispositions.{name} has an unexpected shape")
        if entry["disposition"] != expected or entry["action_taken"] is not False:
            raise ReviewError(
                f"requested_dispositions.{name} drifted or claims an action"
            )
        _nonempty(entry["finding"], f"requested_dispositions.{name}.finding")

    findings = value["global_twenty_lens_findings"]
    if not isinstance(findings, list) or len(findings) != 20:
        raise ReviewError("global findings must contain exactly twenty lenses")
    for number, (finding, source_lens) in enumerate(
        zip(findings, index["twenty_lenses"])
    ):
        path = f"global_twenty_lens_findings[{number}]"
        if not isinstance(finding, dict) or set(finding) != {
            "id",
            "name",
            "finding",
            "residual_risk",
            "status",
        }:
            raise ReviewError(f"{path} has an unexpected shape")
        if finding["id"] != source_lens["id"] or finding["name"] != source_lens["name"]:
            raise ReviewError(f"{path} differs from the exact source lens")
        if finding["status"] != "OPEN":
            raise ReviewError(f"{path}.status must remain OPEN")
        _nonempty(finding["finding"], f"{path}.finding")
        _nonempty(finding["residual_risk"], f"{path}.residual_risk")

    tasks = value["tasks"]
    if not isinstance(tasks, list) or len(tasks) != 146:
        raise ReviewError("review must contain exactly 146 task records")
    expected_fields = {
        "id",
        "state",
        "implementation_coverage",
        "lens_statuses",
        "evidence_summary",
        "acceptance_gap",
        "evidence",
        "residual_risk",
        "reviewer_comment",
    }
    identifiers: list[str] = []
    for number, task in enumerate(tasks):
        path = f"tasks[{number}]"
        if not isinstance(task, dict) or set(task) != expected_fields:
            raise ReviewError(f"{path} has an unexpected shape")
        identifier = _nonempty(task["id"], f"{path}.id")
        identifiers.append(identifier)
        if identifier != index["tasks"][number]["id"]:
            raise ReviewError(f"{path}.id differs from the exact ordered source index")
        if task["state"] != "OPEN":
            raise ReviewError(f"{path}.state must remain OPEN")
        if task["implementation_coverage"] not in COVERAGE:
            raise ReviewError(
                f"{path}.implementation_coverage is invalid or overclaims COMPLETE"
            )
        lens_statuses = task["lens_statuses"]
        if not isinstance(lens_statuses, dict) or tuple(lens_statuses) != LENS_IDS:
            raise ReviewError(
                f"{path}.lens_statuses must contain ordered L01 through L20"
            )
        if any(status != "OPEN" for status in lens_statuses.values()):
            raise ReviewError(f"{path}.lens_statuses must all remain OPEN")
        _nonempty(task["evidence_summary"], f"{path}.evidence_summary")
        _nonempty(task["acceptance_gap"], f"{path}.acceptance_gap")
        _nonempty(task["residual_risk"], f"{path}.residual_risk")
        evidence = task["evidence"]
        if not isinstance(evidence, dict) or set(evidence) != {"paths", "commands"}:
            raise ReviewError(f"{path}.evidence has an unexpected shape")
        evidence_paths = _strings(evidence["paths"], f"{path}.evidence.paths")
        _strings(evidence["commands"], f"{path}.evidence.commands")
        for evidence_number, evidence_path in enumerate(evidence_paths):
            _validate_evidence_path(
                evidence_path, f"{path}.evidence.paths[{evidence_number}]"
            )
        comment = task["reviewer_comment"]
        if comment is not None:
            _nonempty(comment, f"{path}.reviewer_comment")
    if tuple(identifiers) != TASK_IDS:
        raise ReviewError("review task IDs must be exact ordered T000 through T145")
    if _review_content(value) != EXPECTED_REVIEW_CONTENT_SHA256:
        raise ReviewError("non-comment review content differs from the reviewed guard")


def validate_files() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if _sha256(INDEX) != EXPECTED_INDEX_SHA256:
        raise ReviewError(
            "max-effort source index bytes differ from the frozen extract"
        )
    if _sha256(AUDIT) != EXPECTED_AUDIT_SHA256:
        raise ReviewError("max-effort audit-input bytes differ from the reviewed cut")
    index = load(INDEX)
    audit = load(AUDIT)
    review = load(REVIEW)
    validate_index(index)
    validate_audit(audit)
    validate_repository_evidence(audit)
    validate_review(review, index)
    return index, audit, review


def _must_fail(callback: Any, label: str) -> None:
    try:
        callback()
    except ReviewError:
        return
    raise AssertionError(f"hostile mutation passed: {label}")


def self_test(
    index: dict[str, Any], audit: dict[str, Any], review: dict[str, Any]
) -> None:
    release = copy.deepcopy(review)
    release["release_authorized"] = True
    _must_fail(lambda: validate_review(release, index), "release authorization")

    complete = copy.deepcopy(review)
    complete["tasks"][0]["state"] = "COMPLETE"
    _must_fail(lambda: validate_review(complete, index), "task completion")

    completed_lens = copy.deepcopy(review)
    completed_lens["tasks"][0]["lens_statuses"]["L01"] = "COMPLETE"
    _must_fail(lambda: validate_review(completed_lens, index), "lens completion")

    missing = copy.deepcopy(review)
    del missing["tasks"][17]
    _must_fail(lambda: validate_review(missing, index), "missing task")

    reordered = copy.deepcopy(review)
    reordered["tasks"][40], reordered["tasks"][41] = (
        reordered["tasks"][41],
        reordered["tasks"][40],
    )
    _must_fail(lambda: validate_review(reordered, index), "reordered tasks")

    bad_comment = copy.deepcopy(review)
    bad_comment["tasks"][0]["reviewer_comment"] = []
    _must_fail(lambda: validate_review(bad_comment, index), "non-string comment")

    good_comment = copy.deepcopy(review)
    good_comment["tasks"][0]["reviewer_comment"] = "Review this evidence boundary."
    validate_review(good_comment, index)
    if _review_content(good_comment) != _review_content(review):
        raise AssertionError("reviewer comments changed the frozen review content hash")

    bad_source = copy.deepcopy(index)
    bad_source["tasks"][10]["title"] += " drift"
    _must_fail(lambda: validate_index(bad_source), "source title drift")

    bad_dependency = copy.deepcopy(index)
    bad_dependency["tasks"][10]["dependencies"] = ["T008"]
    _must_fail(lambda: validate_index(bad_dependency), "source dependency drift")

    bad_audit = copy.deepcopy(audit)
    bad_audit["scope"]["release_allowed"] = True
    _must_fail(lambda: validate_audit(bad_audit), "audit release claim")

    bad_vectors = copy.deepcopy(audit)
    bad_vectors["normative_identities"]["required_vectors"] = 268
    _must_fail(lambda: validate_audit(bad_vectors), "stale 268-vector count")

    frozen_vectors = copy.deepcopy(audit)
    frozen_vectors["normative_identities"]["required_vectors"] = 269
    frozen_vectors["normative_identities"]["stable_vectors"] = 262
    _must_fail(lambda: validate_audit(frozen_vectors), "frozen 269-vector count")

    bad_diff = copy.deepcopy(audit)
    bad_diff["source_cuts"]["intervening_diff"]["binary_full_index_patch_sha256"] = (
        "0" * 64
    )
    _must_fail(
        lambda: validate_repository_evidence(bad_diff), "intervening diff digest"
    )

    bad_locked = copy.deepcopy(audit)
    bad_locked["locked_inputs"]["Cargo.lock"] = "0" * 64
    _must_fail(lambda: validate_repository_evidence(bad_locked), "locked input digest")

    bad_ledger = copy.deepcopy(audit)
    bad_ledger["reviewed_source_inventory"]["corrected_review_csv_sha256"] = "0" * 64
    _must_fail(lambda: validate_repository_evidence(bad_ledger), "file ledger digest")

    escaped = copy.deepcopy(review)
    escaped["tasks"][0]["evidence"]["paths"][0] = "../outside"
    _must_fail(lambda: validate_review(escaped, index), "path escape")

    absolute = copy.deepcopy(review)
    absolute["tasks"][0]["evidence"]["paths"][0] = "/etc/passwd"
    _must_fail(lambda: validate_review(absolute, index), "absolute evidence path")

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        target = root / "target.txt"
        target.write_text("evidence", encoding="utf-8")
        link = root / "link.txt"
        link.symlink_to(target)
        _must_fail(
            lambda: _validate_evidence_path("link.txt", "self-test.path", root),
            "symlink evidence path",
        )
        duplicate = root / "duplicate.json"
        duplicate.write_text('{"a": 1, "a": 2}', encoding="utf-8")
        _must_fail(lambda: load(duplicate), "duplicate JSON key")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        index, audit, review = validate_files()
        if args.self_test:
            self_test(index, audit, review)
    except (ReviewError, AssertionError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        "OK max-effort handoff review: 146 OPEN tasks, 2920 OPEN lenses, "
        "NO_GO; reviewer comments are the only mutable fields"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
