#!/usr/bin/env python3
"""Validate the retained threat, latent-path, and traceability artifacts.

Generation provides reproducibility; this checker independently enforces the
semantic invariants that keep the records fail-closed and non-authorizing.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import generate_audit_artifacts as generator


ROOT = Path(__file__).resolve().parents[1]
THREAT_REGISTER = ROOT / "evidence" / "audit" / "threat-register.v1.json"
LATENT_INVENTORY = ROOT / "evidence" / "audit" / "latent-path-inventory.v1.json"
TRACEABILITY = ROOT / "evidence" / "audit" / "requirement-traceability.v1.json"
MANIFEST = ROOT / "evidence" / "audit" / "manifest.v1.json"

ARTIFACTS = {
    "evidence/audit/threat-register.v1.json": THREAT_REGISTER,
    "evidence/audit/latent-path-inventory.v1.json": LATENT_INVENTORY,
    "evidence/audit/requirement-traceability.v1.json": TRACEABILITY,
    "evidence/audit/manifest.v1.json": MANIFEST,
}

EXPECTED_DIMENSIONS = (
    "inputs",
    "validation",
    "state",
    "transitions",
    "outputs",
    "errors",
    "resources",
    "time",
    "identity",
    "persistence",
    "concurrency",
    "public_claims",
)
CONTROL_STATUSES = {
    "LOCAL_PREREQUISITES_ONLY",
    "LOCAL_VERIFIED",
    "LOCAL_VERIFIED_NON_CLAIM",
    "LOCAL_VERIFIED_RELEASE_HOLD",
    "LOCAL_VERIFIED_WITH_EXTERNAL_GAP",
    "NOT_RUN_EXTERNAL",
    "PARTIAL_LOCAL",
}
EVIDENCE_STATUSES = {
    "LOCAL_VERIFIED",
    "NOT_CLAIMED",
    "NOT_RUN_EXTERNAL",
    "NOT_RUN_POST_PUBLICATION",
    "PARTIAL_LOCAL",
}
TRACE_KINDS = {
    "candidate-status-claim",
    "explicit-non-claim",
    "extension-policy-claim",
    "normative-precedence-claim",
    "normative-requirement",
    "package-claim",
    "plane-claim",
    "post-release-gate",
    "pre-release-gate",
    "stateful-acceptance-claim",
    "surface-claim",
    "threat-control",
}
PATH_FIELDS = ("code_paths", "test_paths", "evidence_paths")
NODE_LIST_FIELDS = (
    "source_refs",
    "code_paths",
    "test_paths",
    "evidence_paths",
    "verification_commands",
)
OCCURRENCE_ID = re.compile(r"^NCP-LATENT-[0-9A-F]{20}$")


class AuditArtifactError(ValueError):
    """The retained audit artifacts are stale, incomplete, or overclaiming."""


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, member in pairs:
        if key in value:
            raise AuditArtifactError(f"duplicate JSON key {key!r}")
        value[key] = member
    return value


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_no_duplicates,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AuditArtifactError(
            f"cannot read {path.relative_to(ROOT)}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise AuditArtifactError(f"{path.relative_to(ROOT)} must be one JSON object")
    return value


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _slug(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
    if not result:
        raise AuditArtifactError(f"cannot form identifier from {value!r}")
    return result


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditArtifactError(message)


def _header(value: dict[str, Any], schema: str, task: str) -> None:
    _require(value.get("schema") == schema, f"{task} has the wrong schema")
    _require(value.get("normative") is False, f"{task} must remain non-normative")
    _require(
        value.get("candidate") == generator.package_version(),
        f"{task} candidate differs from the workspace package version",
    )
    _require(value.get("wire_version") == "1.0", f"{task} has the wrong wire version")
    _require(
        value.get("generated_by") == generator.GENERATOR,
        f"{task} has the wrong generator identity",
    )
    _require(value.get("task") == task, f"{task} task identity is missing")
    _require(
        value.get("claim_boundary") == generator.CLAIM_BOUNDARY,
        f"{task} claim boundary is missing or changed",
    )


def _safe_repo_path(value: Any, context: str) -> Path:
    _require(
        isinstance(value, str) and value != "", f"{context} must be non-empty text"
    )
    path_text = value.split("#", 1)[0]
    path = Path(path_text)
    _require(
        not path.is_absolute() and ".." not in path.parts,
        f"{context} escapes the repository: {value!r}",
    )
    target = ROOT / path
    _require(target.is_file(), f"{context} does not name a repository file: {value!r}")
    return target


def _resolve_json_pointer(document: Any, pointer: str, context: str) -> Any:
    current = document
    for raw in pointer[1:].split("/") if pointer != "/" else [""]:
        member = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            _require(member.isdigit(), f"{context} has a non-numeric array member")
            index = int(member)
            _require(index < len(current), f"{context} array index is out of range")
            current = current[index]
        elif isinstance(current, dict):
            _require(member in current, f"{context} object member does not exist")
            current = current[member]
        else:
            raise AuditArtifactError(f"{context} traverses through a scalar")
    return current


def _validate_reference(value: Any, context: str) -> None:
    target = _safe_repo_path(value, context)
    text = str(value)
    if "#" not in text:
        return
    fragment = text.split("#", 1)[1]
    if target.suffix == ".json" and fragment.startswith("/"):
        document = load_json(target)
        _resolve_json_pointer(document, fragment, context)


def _nonempty_text(value: Any, context: str) -> None:
    _require(isinstance(value, str) and value.strip() != "", f"{context} must be text")


def _nonempty_text_list(value: Any, context: str) -> list[str]:
    _require(isinstance(value, list) and value, f"{context} must be a non-empty array")
    for index, member in enumerate(value):
        _nonempty_text(member, f"{context}[{index}]")
    _require(len(value) == len(set(value)), f"{context} contains duplicates")
    return value


def validate_threat_register(value: dict[str, Any]) -> None:
    _header(value, "ncp.audit-threat-register.v1", "T004")
    _require(
        value.get("risk_status") == "OPEN", "T004 top-level risk status must be OPEN"
    )
    assumptions = _nonempty_text_list(value.get("assumptions"), "T004 assumptions")
    boundaries = _nonempty_text_list(
        value.get("trust_boundaries"), "T004 trust boundaries"
    )
    _require(len(assumptions) >= 5, "T004 omits system assumptions")
    _require(len(boundaries) >= 8, "T004 omits trust boundaries")

    dimensions = value.get("current_behavior_dimensions")
    _require(
        isinstance(dimensions, list),
        "T004 current behavior dimensions must be an array",
    )
    names: list[str] = []
    for index, member in enumerate(dimensions):
        _require(isinstance(member, dict), f"T004 dimension[{index}] must be an object")
        _require(
            set(member) == {"dimension", "current_behavior"},
            f"T004 dimension[{index}] has unknown or missing fields",
        )
        _nonempty_text(member["dimension"], f"T004 dimension[{index}].dimension")
        _nonempty_text(
            member["current_behavior"], f"T004 dimension[{index}].current_behavior"
        )
        names.append(member["dimension"])
    _require(
        tuple(names) == EXPECTED_DIMENSIONS, "T004 behavior dimensions are not exact"
    )

    counterfactuals = value.get("mandatory_counterfactuals")
    _require(isinstance(counterfactuals, list), "T004 counterfactuals must be an array")
    expected_counterfactuals = [
        {"id": identifier, "scenario": scenario}
        for identifier, scenario in generator.COUNTERFACTUALS.items()
    ]
    _require(
        counterfactuals == expected_counterfactuals,
        "T004 mandatory counterfactual set is not exact",
    )

    threats = value.get("threats")
    _require(isinstance(threats, list), "T004 threats must be an array")
    expected_ids = [f"NCP-THREAT-{number:03d}" for number in range(1, 19)]
    _require(
        [item.get("id") for item in threats] == expected_ids,
        "T004 threat IDs are not exact",
    )
    control_ids: list[str] = []
    covered: set[str] = set()
    required_text = (
        "title",
        "category",
        "boundary",
        "asset_or_claim",
        "actor_or_trigger",
        "misuse_or_failure",
        "accepted_case",
        "rejected_case",
        "impact",
        "failure_response",
        "residual_risk",
    )
    required_lists = (
        "preconditions",
        "detection",
        "prevention",
        "counterfactual_ids",
        "requirement_ids",
        "code_paths",
        "test_paths",
        "verification_commands",
        "evidence_paths",
    )
    for index, threat in enumerate(threats):
        context = f"T004 threat {expected_ids[index]}"
        _require(isinstance(threat, dict), f"{context} must be an object")
        for field in required_text:
            _nonempty_text(threat.get(field), f"{context}.{field}")
        for field in required_lists:
            _nonempty_text_list(threat.get(field), f"{context}.{field}")
        control_id = f"NCP-THREAT-REQ-{index + 1:03d}"
        _require(
            threat.get("control_requirement_id") == control_id,
            f"{context} has the wrong control requirement",
        )
        control_ids.append(control_id)
        _require(
            control_id in threat["requirement_ids"],
            f"{context} does not link its control requirement",
        )
        unknown = set(threat["counterfactual_ids"]) - set(generator.COUNTERFACTUALS)
        _require(
            not unknown, f"{context} links unknown counterfactuals: {sorted(unknown)}"
        )
        covered.update(threat["counterfactual_ids"])
        _require(
            threat.get("control_status") in CONTROL_STATUSES,
            f"{context} has invalid status",
        )
        _require(
            threat.get("risk_status") == "OPEN", f"{context} risk must remain OPEN"
        )
        _require(
            isinstance(threat.get("release_blocking"), bool),
            f"{context}.release_blocking must be a boolean",
        )
        expected_blocking = threat["control_status"] != "LOCAL_VERIFIED_NON_CLAIM"
        _require(
            threat["release_blocking"] is expected_blocking,
            f"{context} release effect disagrees with its explicit claim tier",
        )
        _require(
            threat["accepted_case"] != threat["rejected_case"],
            f"{context} accepted and rejected cases are identical",
        )
        for field in PATH_FIELDS:
            for item_index, path in enumerate(threat[field]):
                _safe_repo_path(path, f"{context}.{field}[{item_index}]")
    _require(
        covered == set(generator.COUNTERFACTUALS),
        "T004 threats do not cover every mandatory counterfactual",
    )
    _require(
        len(control_ids) == len(set(control_ids)), "T004 control IDs are duplicated"
    )
    counts = value.get("counts")
    _require(
        counts
        == {
            "threats": len(threats),
            "open_risks": len(threats),
            "release_blocking": sum(threat["release_blocking"] for threat in threats),
        },
        "T004 counts are stale or inconsistent",
    )


def validate_latent_inventory(value: dict[str, Any]) -> None:
    _header(value, "ncp.latent-path-inventory.v1", "T006")
    policy = value.get("scan_policy")
    _require(isinstance(policy, dict), "T006 scan policy must be an object")
    _require(
        policy.get("case_sensitive") is False, "T006 scan must be case-insensitive"
    )
    _require(policy.get("word_bounded") is True, "T006 tokens must be word-bounded")
    expected_catalog = {
        identifier: {"lexeme_sha256": _sha256(lexeme.casefold().encode("utf-8"))}
        for identifier, lexeme in generator.TOKEN_CATALOG.items()
    }
    _require(
        policy.get("token_catalog") == expected_catalog,
        "T006 token catalog is not exact",
    )

    file_inventory = value.get("file_inventory")
    _require(isinstance(file_inventory, dict), "T006 file inventory must be an object")
    object_format = file_inventory.get("git_object_format")
    _require(
        object_format == generator.git_object_format(),
        "T006 Git object format differs from the repository",
    )
    indexed = generator.indexed_paths()
    text_file_entries = file_inventory.get("text_files")
    non_text_entries = file_inventory.get("non_text_files")
    _require(
        isinstance(text_file_entries, list), "T006 text file inventory must be an array"
    )
    _require(
        isinstance(non_text_entries, list),
        "T006 non-text file inventory must be an array",
    )
    inventory_paths: list[str] = []
    for expected_text, entries in (
        (True, text_file_entries),
        (False, non_text_entries),
    ):
        for index, entry in enumerate(entries):
            context = f"T006 {'text' if expected_text else 'non-text'} file[{index}]"
            _require(isinstance(entry, dict), f"{context} must be an object")
            expected_fields = {"path", "bytes", "sha256", "git_blob_oid", "indexed"}
            if not expected_text:
                expected_fields.add("reason")
            _require(set(entry) == expected_fields, f"{context} fields are not exact")
            path = _safe_repo_path(entry["path"], f"{context}.path")
            content = path.read_bytes()
            inventory_paths.append(entry["path"])
            _require(entry["bytes"] == len(content), f"{context} byte count is stale")
            _require(entry["sha256"] == _sha256(content), f"{context} SHA-256 is stale")
            framed = f"blob {len(content)}\0".encode("ascii") + content
            _require(
                entry["git_blob_oid"] == hashlib.new(object_format, framed).hexdigest(),
                f"{context} Git blob identity is stale",
            )
            _require(
                entry["indexed"] is (entry["path"] in indexed),
                f"{context} indexed disposition is stale",
            )
            try:
                decoded = content.decode("utf-8")
                is_text = "\0" not in decoded
            except UnicodeDecodeError:
                is_text = False
            _require(is_text is expected_text, f"{context} text disposition is wrong")
            if not expected_text:
                expected_reason = "NUL_BYTE" if b"\0" in content else "NON_UTF8"
                _require(
                    entry["reason"] == expected_reason, f"{context} reason is wrong"
                )
    _require(
        len(inventory_paths) == len(set(inventory_paths)),
        "T006 file paths are duplicated",
    )
    expected_paths = {
        path
        for path in generator.repository_paths()
        if path
        not in {
            "evidence/audit/latent-path-inventory.v1.json",
            "evidence/audit/manifest.v1.json",
        }
        and (ROOT / path).is_file()
    }
    _require(
        set(inventory_paths) == expected_paths,
        "T006 file inventory scope is incomplete",
    )
    text_paths = [entry["path"] for entry in text_file_entries]
    non_text_paths = [entry["path"] for entry in non_text_entries]
    _require(
        text_paths == sorted(text_paths), "T006 text file inventory is not ordered"
    )
    _require(
        non_text_paths == sorted(non_text_paths),
        "T006 non-text inventory is not ordered",
    )

    occurrences = value.get("occurrences")
    _require(isinstance(occurrences, list), "T006 occurrences must be an array")
    sort_keys: list[tuple[str, int, int, str]] = []
    identifiers: list[str] = []
    token_counts: Counter[str] = Counter()
    disposition_counts: Counter[str] = Counter()
    for index, occurrence in enumerate(occurrences):
        context = f"T006 occurrence[{index}]"
        _require(isinstance(occurrence, dict), f"{context} must be an object")
        expected_fields = {
            "id",
            "path",
            "line",
            "column",
            "token_id",
            "line_sha256",
            "file_sha256",
            "disposition",
            "claim_effect",
            "evidence_paths",
        }
        _require(set(occurrence) == expected_fields, f"{context} fields are not exact")
        identifier = occurrence["id"]
        _require(
            isinstance(identifier, str) and OCCURRENCE_ID.fullmatch(identifier),
            f"{context}.id is invalid",
        )
        identifiers.append(identifier)
        path = _safe_repo_path(occurrence["path"], f"{context}.path")
        _require(
            isinstance(occurrence["line"], int) and occurrence["line"] >= 1,
            f"{context}.line is invalid",
        )
        _require(
            isinstance(occurrence["column"], int) and occurrence["column"] >= 1,
            f"{context}.column is invalid",
        )
        token_id = occurrence["token_id"]
        _require(
            token_id in generator.TOKEN_CATALOG, f"{context} has an unknown token ID"
        )
        _require(
            isinstance(occurrence["disposition"], str)
            and occurrence["disposition"] != "UNREVIEWED_ACTION_PATH",
            f"{context} has no reviewed disposition",
        )
        _nonempty_text(occurrence["claim_effect"], f"{context}.claim_effect")
        evidence_paths = _nonempty_text_list(
            occurrence["evidence_paths"], f"{context}.evidence_paths"
        )
        for evidence_index, evidence in enumerate(evidence_paths):
            _safe_repo_path(evidence, f"{context}.evidence_paths[{evidence_index}]")

        content = path.read_bytes()
        _require(b"\0" not in content, f"{context} points to binary content")
        try:
            lines = content.decode("utf-8").splitlines()
        except UnicodeDecodeError as error:
            raise AuditArtifactError(
                f"{context} points to non-UTF-8 content"
            ) from error
        _require(occurrence["line"] <= len(lines), f"{context}.line is out of range")
        line = lines[occurrence["line"] - 1]
        lexeme = generator.TOKEN_CATALOG[token_id]
        start = occurrence["column"] - 1
        matched = line[start : start + len(lexeme)]
        _require(
            matched.casefold() == lexeme.casefold(),
            f"{context} no longer matches its token",
        )
        _require(
            _sha256(line.encode("utf-8")) == occurrence["line_sha256"],
            f"{context} line hash is stale",
        )
        _require(
            _sha256(content) == occurrence["file_sha256"],
            f"{context} file hash is stale",
        )
        key_material = (
            f"{occurrence['path']}\0{occurrence['line']}\0{occurrence['column']}"
            f"\0{token_id}\0{occurrence['line_sha256']}"
        )
        expected_id = "NCP-LATENT-" + _sha256(key_material.encode("utf-8"))[:20].upper()
        _require(identifier == expected_id, f"{context} ID is not content-addressed")
        sort_keys.append(
            (occurrence["path"], occurrence["line"], occurrence["column"], token_id)
        )
        token_counts[token_id] += 1
        disposition_counts[occurrence["disposition"]] += 1
    _require(
        len(identifiers) == len(set(identifiers)), "T006 occurrence IDs are duplicated"
    )
    _require(
        sort_keys == sorted(sort_keys),
        "T006 occurrences are not deterministically ordered",
    )
    counts = value.get("counts")
    _require(isinstance(counts, dict), "T006 counts must be an object")
    _require(
        counts.get("occurrences") == len(occurrences), "T006 occurrence count is stale"
    )
    _require(
        counts.get("by_token_id") == dict(sorted(token_counts.items())),
        "T006 token counts are stale",
    )
    _require(
        counts.get("by_disposition") == dict(sorted(disposition_counts.items())),
        "T006 disposition counts are stale",
    )
    _require(
        isinstance(counts.get("text_files"), int) and counts["text_files"] > 0,
        "T006 text-file count is invalid",
    )
    _require(
        counts["text_files"] == len(text_file_entries), "T006 text-file count is stale"
    )
    _require(
        isinstance(counts.get("binary_or_non_utf8_files"), int)
        and counts["binary_or_non_utf8_files"] >= 0,
        "T006 binary-file count is invalid",
    )
    _require(
        counts["binary_or_non_utf8_files"] == len(non_text_entries),
        "T006 non-text file count is stale",
    )
    expected_path_digest = _sha256(
        json.dumps(
            text_paths,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    _require(
        value.get("scanned_path_set_sha256") == expected_path_digest,
        "T006 scanned path-set digest is stale",
    )


def _surface_ids(surface: dict[str, Any]) -> set[str]:
    identifiers = {f"NCP-SURFACE-STATUS-{_slug(surface['status'])}"}
    identifiers.update(
        f"NCP-SURFACE-NORMATIVE-PRECEDENCE-{index + 1:02d}"
        for index, _ in enumerate(surface["normative_precedence"])
    )
    for group in ("messages", "encodings", "transports"):
        for state, members in surface[group].items():
            identifiers.update(
                f"NCP-SURFACE-{_slug(group)}-{_slug(state)}-{_slug(member)}"
                for member in members
            )
    identifiers.update(
        f"NCP-SURFACE-PLANE-{_slug(member)}" for member in surface["planes"]
    )
    identifiers.update(
        f"NCP-SURFACE-STATEFUL-{_slug(member)}"
        for member in surface["stateful_acceptance"]
    )
    identifiers.update(
        f"NCP-SURFACE-EXTENSION-{_slug(member)}" for member in surface["extensions"]
    )
    for state, members in surface["packages"].items():
        identifiers.update(
            f"NCP-SURFACE-PACKAGE-{_slug(state)}-{_slug(member)}" for member in members
        )
    identifiers.update(
        f"NCP-SURFACE-NONCLAIM-{_slug(member)}" for member in surface["non_claims"]
    )
    return identifiers


def _expected_source_refs(threats: dict[str, Any]) -> dict[str, list[str]]:
    conformance = load_json(ROOT / "conformance" / "manifest.v1.json")
    release_gates = load_json(ROOT / "contract" / "release-gates.v1.json")
    surface = load_json(ROOT / "contract" / "surface.v1.json")
    expected = {
        entry["id"]: [entry["source"]]
        for entry in conformance["normative_requirements"]
    }
    for phase, field in (
        ("PRE", "pre_release_gates"),
        ("POST", "post_release_validations"),
    ):
        for index, entry in enumerate(release_gates[field]):
            expected[f"NCP-RELEASE-{phase}-{_slug(entry['id'])}"] = [
                f"contract/release-gates.v1.json#/{field}/{index}"
            ]
    expected[f"NCP-SURFACE-STATUS-{_slug(surface['status'])}"] = [
        "contract/surface.v1.json#/status"
    ]
    for index, _ in enumerate(surface["normative_precedence"]):
        expected[f"NCP-SURFACE-NORMATIVE-PRECEDENCE-{index + 1:02d}"] = [
            f"contract/surface.v1.json#/normative_precedence/{index}"
        ]
    for group in ("messages", "encodings", "transports"):
        for state, members in surface[group].items():
            for index, member in enumerate(members):
                expected[
                    f"NCP-SURFACE-{_slug(group)}-{_slug(state)}-{_slug(member)}"
                ] = [f"contract/surface.v1.json#/{group}/{state}/{index}"]
    for index, member in enumerate(surface["planes"]):
        expected[f"NCP-SURFACE-PLANE-{_slug(member)}"] = [
            f"contract/surface.v1.json#/planes/{index}"
        ]
    for member in surface["stateful_acceptance"]:
        expected[f"NCP-SURFACE-STATEFUL-{_slug(member)}"] = [
            f"contract/surface.v1.json#/stateful_acceptance/{member}"
        ]
    for member in surface["extensions"]:
        expected[f"NCP-SURFACE-EXTENSION-{_slug(member)}"] = [
            f"contract/surface.v1.json#/extensions/{member}"
        ]
    for state, members in surface["packages"].items():
        for index, member in enumerate(members):
            expected[f"NCP-SURFACE-PACKAGE-{_slug(state)}-{_slug(member)}"] = [
                f"contract/surface.v1.json#/packages/{state}/{index}"
            ]
    for index, member in enumerate(surface["non_claims"]):
        expected[f"NCP-SURFACE-NONCLAIM-{_slug(member)}"] = [
            f"contract/surface.v1.json#/non_claims/{index}"
        ]
    for index, threat in enumerate(threats["threats"]):
        expected[threat["control_requirement_id"]] = [
            f"evidence/audit/threat-register.v1.json#/threats/{index}"
        ]
    return expected


def _release_ids(release_gates: dict[str, Any]) -> dict[str, tuple[str, str, str]]:
    expected: dict[str, tuple[str, str, str]] = {}
    for entry in release_gates["pre_release_gates"]:
        identifier = f"NCP-RELEASE-PRE-{_slug(entry['id'])}"
        if entry["local"]:
            expected[identifier] = (
                "LOCAL_VERIFIED",
                "local-source-bound-evidence",
                "local-guard",
            )
        else:
            expected[identifier] = (
                "NOT_RUN_EXTERNAL",
                "external-evidence-required",
                "release-blocking-open",
            )
    for entry in release_gates["post_release_validations"]:
        identifier = f"NCP-RELEASE-POST-{_slug(entry['id'])}"
        expected[identifier] = (
            "NOT_RUN_POST_PUBLICATION",
            "post-publication-evidence-required",
            "post-publication-nonblocking",
        )
    return expected


def _expected_trace_ids(threats: dict[str, Any]) -> tuple[set[str], dict[str, int]]:
    conformance = load_json(ROOT / "conformance" / "manifest.v1.json")
    release_gates = load_json(ROOT / "contract" / "release-gates.v1.json")
    surface = load_json(ROOT / "contract" / "surface.v1.json")
    normative = {entry["id"] for entry in conformance["normative_requirements"]}
    release = set(_release_ids(release_gates))
    surface_ids = _surface_ids(surface)
    controls = {entry["control_requirement_id"] for entry in threats["threats"]}
    union = normative | release | surface_ids | controls
    counts = {
        "normative_requirements": len(normative),
        "release_gates": len(release),
        "surface_claims": len(surface_ids),
        "threat_controls": len(controls),
    }
    _require(sum(counts.values()) == len(union), "trace source universes overlap")
    return union, counts


def validate_traceability(value: dict[str, Any], threats: dict[str, Any]) -> None:
    _header(value, "ncp.requirement-traceability.v1", "T008")
    expected_ids, source_counts = _expected_trace_ids(threats)
    _require(
        value.get("source_set_counts") == source_counts, "T008 source counts are stale"
    )
    requirements = value.get("requirements")
    _require(isinstance(requirements, list), "T008 requirements must be an array")
    identifiers = [item.get("id") for item in requirements if isinstance(item, dict)]
    _require(
        len(identifiers) == len(requirements), "T008 contains a non-object requirement"
    )
    _require(identifiers == sorted(identifiers), "T008 requirements are not ordered")
    _require(
        len(identifiers) == len(set(identifiers)), "T008 requirement IDs are duplicated"
    )
    _require(
        set(identifiers) == expected_ids, "T008 requirement universe is incomplete"
    )
    requirements_by_id = {item["id"]: item for item in requirements}
    expected_source_refs = _expected_source_refs(threats)
    _require(
        set(expected_source_refs) == expected_ids,
        "T008 expected source-reference universe is incomplete",
    )

    release_gates = load_json(ROOT / "contract" / "release-gates.v1.json")
    release_expectations = _release_ids(release_gates)
    conformance = load_json(ROOT / "conformance" / "manifest.v1.json")
    vectors_by_requirement = {
        entry["id"]: entry["vector_ids"]
        for entry in conformance["normative_requirements"]
    }
    threat_ids = {entry["id"] for entry in threats["threats"]}
    control_statuses = {
        entry["control_requirement_id"]: entry["control_status"]
        for entry in threats["threats"]
    }
    for threat in threats["threats"]:
        for requirement_id in threat["requirement_ids"]:
            _require(
                requirement_id in requirements_by_id,
                f"T008 omits {threat['id']} requirement link {requirement_id}",
            )
            _require(
                threat["id"] in requirements_by_id[requirement_id]["threat_ids"],
                f"T008 does not reciprocate {threat['id']} link to {requirement_id}",
            )
    status_counts: Counter[str] = Counter()
    expected_edges: list[dict[str, str]] = []
    for requirement in requirements:
        identifier = requirement["id"]
        context = f"T008 requirement {identifier}"
        _nonempty_text(identifier, f"{context}.id")
        _require(
            requirement.get("kind") in TRACE_KINDS, f"{context} has an unknown kind"
        )
        _nonempty_text(requirement.get("requirement"), f"{context}.requirement")
        _require(
            requirement.get("source_refs") == expected_source_refs[identifier],
            f"{context} does not point to its exact source claim",
        )
        for field in NODE_LIST_FIELDS:
            members = _nonempty_text_list(requirement.get(field), f"{context}.{field}")
            for index, member in enumerate(members):
                if field == "source_refs":
                    _validate_reference(member, f"{context}.{field}[{index}]")
                elif field != "verification_commands":
                    _safe_repo_path(member, f"{context}.{field}[{index}]")
        status = requirement.get("evidence_status")
        _require(
            status in EVIDENCE_STATUSES, f"{context} has an invalid evidence status"
        )
        status_counts[status] += 1
        _nonempty_text(requirement.get("claim_tier"), f"{context}.claim_tier")
        _nonempty_text(requirement.get("release_effect"), f"{context}.release_effect")
        linked_threats = requirement.get("threat_ids")
        vectors = requirement.get("vector_ids")
        _require(
            isinstance(linked_threats, list), f"{context}.threat_ids must be an array"
        )
        _require(isinstance(vectors, list), f"{context}.vector_ids must be an array")
        _require(
            len(linked_threats) == len(set(linked_threats)),
            f"{context} repeats threats",
        )
        _require(
            not (set(linked_threats) - threat_ids), f"{context} links unknown threats"
        )
        if identifier in vectors_by_requirement:
            _require(
                vectors == vectors_by_requirement[identifier],
                f"{context} vector coverage differs from conformance",
            )
        elif requirement["kind"] != "normative-requirement":
            _require(vectors == [], f"{context} invents vector coverage")
        if identifier in release_expectations:
            expected_status, tier, effect = release_expectations[identifier]
            _require(
                (status, requirement["claim_tier"], requirement["release_effect"])
                == (expected_status, tier, effect),
                f"{context} overstates or misphases release evidence",
            )
        if requirement["kind"] == "threat-control":
            control = control_statuses[identifier]
            expected_status = (
                "NOT_RUN_EXTERNAL"
                if control == "NOT_RUN_EXTERNAL"
                else "PARTIAL_LOCAL"
                if control
                in {
                    "PARTIAL_LOCAL",
                    "LOCAL_PREREQUISITES_ONLY",
                    "LOCAL_VERIFIED_WITH_EXTERNAL_GAP",
                }
                else "LOCAL_VERIFIED"
            )
            _require(
                status == expected_status, f"{context} disagrees with its open control"
            )
            source_threat = next(
                threat
                for threat in threats["threats"]
                if threat["control_requirement_id"] == identifier
            )
            expected_tier = (
                "explicit-non-claim"
                if control == "LOCAL_VERIFIED_NON_CLAIM"
                else (
                    "external-evidence-required"
                    if status == "NOT_RUN_EXTERNAL"
                    else "local-control-with-open-risk"
                )
            )
            expected_effect = (
                "release-blocking-open"
                if source_threat["release_blocking"]
                else "narrowed-claim"
            )
            _require(
                (requirement["claim_tier"], requirement["release_effect"])
                == (expected_tier, expected_effect),
                f"{context} claim tier disagrees with its threat disposition",
            )
        relations = (
            ("code_paths", "implemented-by"),
            ("test_paths", "verified-by"),
            ("evidence_paths", "evidenced-by"),
            ("threat_ids", "mitigates"),
        )
        for field, relation in relations:
            expected_edges.extend(
                {"from": identifier, "relation": relation, "to": member}
                for member in requirement[field]
            )

    edges = value.get("edges")
    _require(isinstance(edges, list), "T008 edges must be an array")
    expected_edges.sort(key=lambda edge: (edge["from"], edge["relation"], edge["to"]))
    _require(edges == expected_edges, "T008 explicit edges are incomplete or stale")
    _require(
        value.get("counts")
        == {
            "requirements": len(requirements),
            "edges": len(edges),
            "by_evidence_status": dict(sorted(status_counts.items())),
        },
        "T008 counts are stale or inconsistent",
    )
    _require(
        release_gates.get("release_allowed") is False,
        "release policy unexpectedly allows release",
    )


def validate_manifest(
    value: dict[str, Any], documents: dict[str, dict[str, Any]]
) -> None:
    _require(
        value.get("schema") == "ncp.audit-evidence-manifest.v1",
        "manifest schema is wrong",
    )
    _require(
        value.get("normative") is False, "audit manifest must remain non-normative"
    )
    _require(
        value.get("candidate") == generator.package_version(),
        "manifest candidate is stale",
    )
    _require(value.get("wire_version") == "1.0", "manifest wire version is wrong")
    _require(
        value.get("generated_by") == generator.GENERATOR, "manifest generator is wrong"
    )
    _require(
        value.get("claim_boundary") == generator.CLAIM_BOUNDARY,
        "manifest claim boundary is missing or changed",
    )
    artifacts = value.get("artifacts")
    _require(isinstance(artifacts, list), "manifest artifacts must be an array")
    expected_paths = set(ARTIFACTS) - {"evidence/audit/manifest.v1.json"}
    _require(
        {entry.get("path") for entry in artifacts} == expected_paths,
        "manifest artifact set is wrong",
    )
    record_fields = {
        "evidence/audit/threat-register.v1.json": ("counts", "threats"),
        "evidence/audit/latent-path-inventory.v1.json": ("counts", "occurrences"),
        "evidence/audit/requirement-traceability.v1.json": ("counts", "requirements"),
    }
    for entry in artifacts:
        _require(
            set(entry) == {"path", "sha256", "bytes", "records"},
            "manifest artifact fields are wrong",
        )
        path = _safe_repo_path(entry["path"], "manifest artifact path")
        content = path.read_bytes()
        _require(
            entry["sha256"] == _sha256(content),
            f"manifest hash is stale for {entry['path']}",
        )
        _require(
            entry["bytes"] == len(content),
            f"manifest byte count is stale for {entry['path']}",
        )
        outer, inner = record_fields[entry["path"]]
        _require(
            entry["records"] == documents[entry["path"]][outer][inner],
            f"manifest record count is stale for {entry['path']}",
        )

    sources = value.get("source_inputs")
    _require(isinstance(sources, list), "manifest source inputs must be an array")
    expected_sources = {
        "contract/surface.v1.json",
        "contract/release-gates.v1.json",
        "conformance/manifest.v1.json",
        "contract/manifest.v1.json",
        "Cargo.lock",
        "bun.lock",
        "evidence/supply-chain/vulnerability-report.v1.json",
    }
    _require(
        {entry.get("path") for entry in sources} == expected_sources,
        "manifest source set is wrong",
    )
    for entry in sources:
        _require(
            set(entry) == {"path", "sha256", "bytes"},
            "manifest source fields are wrong",
        )
        path = _safe_repo_path(entry["path"], "manifest source path")
        content = path.read_bytes()
        _require(
            entry["sha256"] == _sha256(content),
            f"manifest source hash is stale for {entry['path']}",
        )
        _require(
            entry["bytes"] == len(content),
            f"manifest source size is stale for {entry['path']}",
        )


def _assert_token_free(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"\b(?:"
        + "|".join(re.escape(value) for value in generator.TOKEN_CATALOG.values())
        + r")\b",
        re.IGNORECASE,
    )
    _require(
        pattern.search(text) is None, f"{path.relative_to(ROOT)} must remain token-free"
    )


def validate_all(documents: dict[str, dict[str, Any]]) -> None:
    threats = documents["evidence/audit/threat-register.v1.json"]
    latent = documents["evidence/audit/latent-path-inventory.v1.json"]
    trace = documents["evidence/audit/requirement-traceability.v1.json"]
    manifest = documents["evidence/audit/manifest.v1.json"]
    validate_threat_register(threats)
    validate_latent_inventory(latent)
    validate_traceability(trace, threats)
    validate_manifest(manifest, documents)
    _assert_token_free(LATENT_INVENTORY)
    _assert_token_free(MANIFEST)


def check_freshness() -> dict[str, dict[str, Any]]:
    expected = generator.build_artifacts()
    stale: list[str] = []
    for path, content in expected.items():
        target = ROOT / path
        if not target.is_file() or target.read_bytes() != content:
            stale.append(path)
    if stale:
        raise AuditArtifactError(
            "generated audit artifacts are missing or stale: "
            + ", ".join(stale)
            + "; run scripts/generate_audit_artifacts.py --write and review"
        )
    return {path: load_json(target) for path, target in ARTIFACTS.items()}


def _must_fail(function: Callable[..., None], *args: Any) -> None:
    try:
        function(*args)
    except AuditArtifactError:
        return
    raise AssertionError(f"hostile mutation passed {function.__name__}")


def self_test(documents: dict[str, dict[str, Any]]) -> None:
    hostile = copy.deepcopy(documents["evidence/audit/threat-register.v1.json"])
    hostile["mandatory_counterfactuals"].pop()
    _must_fail(validate_threat_register, hostile)

    hostile = copy.deepcopy(documents["evidence/audit/latent-path-inventory.v1.json"])
    hostile["occurrences"][0]["disposition"] = "UNREVIEWED_ACTION_PATH"
    _must_fail(validate_latent_inventory, hostile)

    threats = documents["evidence/audit/threat-register.v1.json"]
    hostile = copy.deepcopy(
        documents["evidence/audit/requirement-traceability.v1.json"]
    )
    external = next(
        item
        for item in hostile["requirements"]
        if item["kind"] == "pre-release-gate"
        and item["evidence_status"] == "NOT_RUN_EXTERNAL"
    )
    external["evidence_status"] = "LOCAL_VERIFIED"
    _must_fail(validate_traceability, hostile, threats)

    hostile = copy.deepcopy(
        documents["evidence/audit/requirement-traceability.v1.json"]
    )
    hostile["edges"].pop()
    _must_fail(validate_traceability, hostile, threats)

    hostile = copy.deepcopy(
        documents["evidence/audit/requirement-traceability.v1.json"]
    )
    hostile["requirements"][0]["code_paths"][0] = "missing/audit-code-path"
    _must_fail(validate_traceability, hostile, threats)

    hostile_documents = copy.deepcopy(documents)
    hostile_manifest = hostile_documents["evidence/audit/manifest.v1.json"]
    hostile_manifest["artifacts"][0]["sha256"] = "0" * 64
    _must_fail(validate_manifest, hostile_manifest, hostile_documents)

    try:
        json.loads(
            '{"duplicate":1,"duplicate":2}', object_pairs_hook=_object_no_duplicates
        )
    except AuditArtifactError:
        pass
    else:
        raise AssertionError("duplicate JSON member passed hostile test")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="also run hostile semantic mutations",
    )
    args = parser.parse_args()
    try:
        documents = check_freshness()
        validate_all(documents)
        if args.self_test:
            self_test(documents)
    except (AuditArtifactError, AssertionError, KeyError, TypeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    threats = documents["evidence/audit/threat-register.v1.json"]["counts"]["threats"]
    latent = documents["evidence/audit/latent-path-inventory.v1.json"]["counts"][
        "occurrences"
    ]
    requirements = documents["evidence/audit/requirement-traceability.v1.json"][
        "counts"
    ]["requirements"]
    edges = documents["evidence/audit/requirement-traceability.v1.json"]["counts"][
        "edges"
    ]
    print(
        "OK retained audit semantics: "
        f"{threats} open threats, {latent} reviewed marker occurrences, "
        f"{requirements} requirements, {edges} explicit edges"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
