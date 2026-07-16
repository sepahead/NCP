#!/usr/bin/env python3
"""Validate the NCP 1.0 implementation ledger without third-party packages.

The ledger is evidence bookkeeping. It cannot authorize runtime behavior, a tag,
publication, certification, or a scientific/physical-safety claim.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "evidence" / "implementation" / "task-ledger.v1.json"
BLUEPRINT = ROOT / "docs" / "handoff" / "NCP_V1_0_ECOSYSTEM_FINALIZATION_BLUEPRINT.md"

SCHEMA_ID = "ncp.implementation-task-ledger.v1"
STATUSES = (
    "OPEN",
    "IN_PROGRESS",
    "BLOCKED",
    "LOCAL_PASS",
    "EXTERNAL_PASS",
    "INDEPENDENT_PASS",
    "COMPLETE",
)
LENSES = tuple(f"L{number}" for number in range(1, 11))
PERSPECTIVES = ("P1", "P2", "P3")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
TASK_ID = re.compile(r"^[BEHNFGCPXR][0-9]{2}$")
TIMESTAMP = re.compile(r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
RELATIVE_PATH = re.compile(r"^(?!/)(?![A-Za-z]:[\\/])(?!.*(?:^|/)\.\.(?:/|$)).+$")
ABSOLUTE_LOCAL_PATH = re.compile(
    r"(?:^|[=:\s\"'`])(?:file://)?(?:/(?!/)[^\s\"'`]+|[A-Za-z]:[\\/][^\s\"'`]+)"
)
SECRET = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{20,}|"
    r"\bAKIA[0-9A-Z]{16}\b|\bsk-[A-Za-z0-9_-]{20,}|\beyJ[A-Za-z0-9_-]{20,}\."
    r"[A-Za-z0-9_-]{10,}\.|\bxox[baprs]-[A-Za-z0-9-]{10,}|\bglpat-[A-Za-z0-9_-]{10,}|"
    r"\bnpm_[A-Za-z0-9]{20,}|\bpypi-[A-Za-z0-9_-]{20,}|https?://[^\s/:]+:[^\s/@]+@|"
    r"\"type\"\s*:\s*\"service_account\"",
    re.IGNORECASE,
)
MAX_EVIDENCE_FILES = 128
MAX_EVIDENCE_FILE_BYTES = 64 * 1024 * 1024
MAX_EVIDENCE_REFERENCES = 1024
MAX_EVIDENCE_REFERENCED_BYTES = 512 * 1024 * 1024

CLAIM_BOUNDARY = (
    "This ledger records bounded implementation progress only. It never authorizes "
    "runtime identity, plant action, a tag, publication, certification, physical safety, "
    "calibrated posterior inference, paper reproduction, or a scientific claim. OPEN and "
    "IN_PROGRESS are not passes; LOCAL_PASS cannot satisfy external or independent gates."
)
REVIEW_MAPPING_SHA256 = (
    "ac7e6f6062d1e8258c30c1335b8dc9d9f90c4ce55c27ddf6c5e094e6b4425716"
)
REPOSITORY_NAMES = (
    "NCP",
    "Engram / Paper2Brain",
    "Haldir",
    "Galadriel",
    "Crebain",
    "Crebain Galadriel producer",
    "Prisoma",
    "pid-rs",
    "sepahead profile",
)


class LedgerError(ValueError):
    """The implementation ledger is invalid or overclaims evidence."""


# This catalog is the checked implementation DAG. Descriptive detail remains in
# the blueprint; status and receipts live only in the JSON ledger.
TASK_CATALOG: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("B00", "Create the live implementation and evidence ledger", (), "NCP"),
    (
        "B04",
        "Prove authenticated-ingress and independent-parser feasibility",
        ("B00",),
        "NCP prototypes",
    ),
    ("B01", "Decide and ratify ADR-001 through ADR-011", ("B00", "B04"), "NCP"),
    (
        "B02",
        "Authorize and identify the deliberate pre-release rebaseline",
        ("B01",),
        "NCP",
    ),
    ("B03", "Reserve registries, namespaces, error codes, and owners", ("B01",), "NCP"),
    (
        "N01",
        "Establish the single normative source graph and identity projections",
        ("B02", "B03"),
        "NCP",
    ),
    (
        "N02",
        "Implement typed simulation, plant, and observer session lifecycles",
        ("N01",),
        "NCP",
    ),
    (
        "N03",
        "Implement declared streams, domain-separated authority, and command disposition",
        ("N01", "N02"),
        "NCP",
    ),
    (
        "N04",
        "Implement the production authenticated envelope and semantic security state",
        ("B01", "N01", "N02"),
        "NCP",
    ),
    (
        "X00",
        "Prototype an early independent non-Rust draft peer",
        ("N02", "N03", "N04"),
        "independent draft-peer environment",
    ),
    (
        "N05",
        "Refactor critical Rust behavior into pure checked transition cores",
        ("N02", "N03", "N04"),
        "NCP",
    ),
    (
        "N06",
        "Integrate security and state machines into Zenoh without trusting callbacks",
        ("N04", "N05"),
        "NCP",
    ),
    (
        "N07",
        "Regenerate and harden all supported language and package surfaces",
        ("N05", "N06", "X00"),
        "NCP",
    ),
    (
        "N08",
        "Rebuild conformance, behavior, migration, and fixture coverage",
        ("N02", "N03", "N04", "N07"),
        "NCP",
    ),
    (
        "N09",
        "Remove supply-chain and package-identity release blockers",
        ("N06", "N07"),
        "NCP",
    ),
    (
        "N10",
        "Rewrite normative and user documentation and regenerate visuals",
        ("N01", "N02", "N03", "N04", "N05", "N06", "N07", "N08", "N09"),
        "NCP",
    ),
    (
        "F01",
        "Implement and independently review the TLA+ model suite",
        ("N02", "N03", "N04"),
        "NCP",
    ),
    (
        "F02",
        "Implement SMT, Kani, and model-to-Rust refinement checks",
        ("N01", "N05", "F01"),
        "NCP",
    ),
    (
        "F03",
        "Implement differential, property, fuzz, sanitizer, and mutation campaigns",
        ("N07", "N08", "F02"),
        "NCP",
    ),
    (
        "R01",
        "Create the final untagged 1.0.0 source cut and publication machinery",
        ("N10", "F03"),
        "NCP",
    ),
    (
        "R11",
        "Establish durable 1.0 stewardship without pretending software is eternal",
        ("N10",),
        "NCP and ecosystem governance",
    ),
    (
        "E01",
        "Establish Engram's clean native-1.0 integration baseline",
        ("N07", "N08", "N09", "R01"),
        "Engram",
    ),
    (
        "H01",
        "Add a parallel haldir-ncp10 adapter without mutating v0.8 history",
        ("N07", "N08", "N09", "R01"),
        "Haldir",
    ),
    (
        "G01",
        "Create Galadriel's native-1.0 observer and extension adapter",
        ("B03", "N07", "N08", "N09", "R01"),
        "Galadriel",
    ),
    (
        "C01",
        "Create Crebain's separate native-1.0 plant adapter and exact pins",
        ("N07", "N08", "N09", "R01"),
        "Crebain",
    ),
    (
        "P01",
        "Add a parallel native-1.0 Prisoma observer",
        ("N07", "N08", "N09", "R01"),
        "Prisoma",
    ),
    (
        "E02",
        "Split Engram's simulation responder from plant commander types",
        ("E01", "N02", "N07"),
        "Engram",
    ),
    (
        "H02",
        "Integrate body-issued authority and dispositions into Haldir Gate",
        ("H01", "N03", "G01"),
        "Haldir",
    ),
    (
        "G02",
        "Bind Galadriel lifecycle and monitoring to authenticated observer state",
        ("G01", "N04", "N06"),
        "Galadriel",
    ),
    (
        "C02",
        "Implement Crebain as body-issued authority and disposition source",
        ("C01", "N03", "N04", "N05", "N06"),
        "Crebain",
    ),
    (
        "P02",
        "Preserve missing-variable and research-claim semantics in native capture",
        ("P01",),
        "Prisoma",
    ),
    (
        "E03",
        "Implement Engram's authenticated transport and declared streams",
        ("E02", "N04", "N06"),
        "Engram",
    ),
    (
        "C03",
        "Migrate Crebain sensor and Galadriel-extension publication",
        ("C02", "G01"),
        "Crebain",
    ),
    (
        "E04",
        "Implement Engram direct and Haldir-gated plant integration",
        ("E02", "E03", "N03", "C02", "H01"),
        "Engram",
    ),
    (
        "C04",
        "Reconcile and retire the separate Galadriel-producer work branch",
        ("C01", "C02", "C03"),
        "Crebain and producer worktree",
    ),
    (
        "X01",
        "Qualify two genuinely independent installed non-Rust peers",
        ("N07", "N08", "E03", "X00"),
        "independent peer lab",
    ),
    (
        "X02",
        "Run the composed ecosystem and multi-writer campaign",
        ("E04", "H02", "G02", "C03", "C04", "P02", "X01"),
        "isolated ecosystem lab",
    ),
    (
        "E05",
        "Certify Engram's exact installed native-1.0 artifact",
        ("E01", "E02", "E03", "E04", "X01", "X02"),
        "Engram certification environment",
    ),
    (
        "H03",
        "Qualify Haldir's secure commander and deny-only receiver roles",
        ("H02", "C02", "X01", "X02"),
        "Haldir certification environment",
    ),
    (
        "G03",
        "Qualify Galadriel's installed observer and deny-only assessor roles",
        ("G01", "G02", "C03", "X01", "X02"),
        "Galadriel certification environment",
    ),
    (
        "P03",
        "Migrate the fault observatory and certify Prisoma's observer role",
        ("P01", "P02", "X01", "X02"),
        "Prisoma certification environment",
    ),
    (
        "F04",
        "Execute the live security, fault, soak, rotation, and revocation campaign",
        ("F03", "X01", "X02"),
        "cross-ecosystem lab",
    ),
    (
        "C05",
        "Certify Crebain body and producer integration separately",
        ("C02", "C03", "C04", "E05", "H03", "G03", "X01", "X02"),
        "Crebain certification environment",
    ),
    (
        "X03",
        "Issue nine exact consumer and extension role qualification receipts",
        ("E05", "H03", "G03", "C05", "P03", "X02", "F04"),
        "cross-ecosystem adjudication",
    ),
    (
        "X04",
        "Reproduce the provider and ecosystem from clean rooms",
        ("X03", "N09"),
        "independent clean builders",
    ),
    (
        "F05",
        "Execute release-bound performance, resource, and final visual campaigns",
        ("N10", "F04", "X03", "X04"),
        "cross-ecosystem lab",
    ),
    (
        "R00",
        "Hand the qualified candidate to the release runbook",
        ("F01", "F02", "F03", "F04", "F05", "N10", "R01", "X03", "X04"),
        "NCP",
    ),
    (
        "R10",
        "Execute rollback, withdrawal, revocation, and incident response",
        ("N10", "F04"),
        "incident-response exercise",
    ),
    (
        "R02",
        "Issue the signed release-authorization bundle",
        ("R00", "R10", "R11"),
        "independent release adjudication",
    ),
    (
        "R03",
        "Create and verify the immutable signed tag and draft GitHub Release",
        ("R02",),
        "NCP release environment",
    ),
    (
        "R04",
        "Build, compare, sign, attest, and stage final artifacts",
        ("R03",),
        "protected release builders",
    ),
    (
        "R05",
        "Publish exact registry artifacts and the GitHub Release",
        ("R04",),
        "protected publication environment",
    ),
    (
        "R06",
        "Update NCP README, GitHub description, topics, and repository controls",
        ("R05",),
        "NCP and GitHub",
    ),
    (
        "R07",
        "Repin and revalidate every consumer against the immutable tag",
        ("R05",),
        "all consumer repositories",
    ),
    (
        "R08",
        "Update ecosystem repository metadata and the public selected-work profile",
        ("R06", "R07"),
        "ecosystem GitHub and profile",
    ),
    (
        "R09",
        "Run post-publication installs and emergency-revocation exercise",
        ("R05",),
        "public install hosts and revocation lab",
    ),
)

MINIMUM_TERMINAL_CLASS: dict[str, str] = {
    **{task_id: "LOCAL" for task_id, _, _, _ in TASK_CATALOG},
    "B01": "INDEPENDENT",
    "B02": "EXTERNAL",
    "N09": "EXTERNAL",
    "F01": "INDEPENDENT",
    "R11": "EXTERNAL",
    "E05": "INDEPENDENT",
    "H03": "INDEPENDENT",
    "G03": "INDEPENDENT",
    "P03": "INDEPENDENT",
    "F04": "EXTERNAL",
    "C05": "INDEPENDENT",
    "X00": "INDEPENDENT",
    "X01": "INDEPENDENT",
    "X02": "EXTERNAL",
    "X03": "INDEPENDENT",
    "X04": "INDEPENDENT",
    "F05": "EXTERNAL",
    "R00": "INDEPENDENT",
    "R10": "EXTERNAL",
    "R02": "INDEPENDENT",
    "R03": "EXTERNAL",
    "R04": "EXTERNAL",
    "R05": "EXTERNAL",
    "R06": "EXTERNAL",
    "R07": "EXTERNAL",
    "R08": "EXTERNAL",
    "R09": "EXTERNAL",
}

INDEPENDENT_REVIEWER_MINIMUM: dict[str, int] = {
    "B01": 2,
    "F01": 2,
    "E05": 1,
    "H03": 1,
    "G03": 1,
    "P03": 1,
    "C05": 1,
    "X00": 1,
    "X01": 2,
    "X03": 2,
    "X04": 2,
    "R00": 2,
    "R02": 2,
}

REQUIRED_EXTERNAL_GATES: dict[str, tuple[str, ...]] = {
    "B02": ("owner-rebaseline-authorization",),
    "N09": ("current-advisory-and-registry-identity",),
    "R11": ("owner-approved-stewardship-policy",),
    "X02": ("composed-ecosystem-multi-writer",),
    "F04": ("live-security-fault-soak-rotation-revocation",),
    "F05": ("release-performance-resource-visual",),
    "R10": ("incident-response-exercise",),
    "R03": ("signed-tag-remote-draft-release",),
    "R04": ("protected-build-sign-attest-stage",),
    "R05": ("registry-and-github-publication",),
    "R06": ("github-metadata-controls-and-clean-install-docs",),
    "R07": ("consumer-tag-repin-and-revalidation",),
    "R08": ("ecosystem-metadata-and-profile",),
    "R09": ("public-install-and-emergency-revocation",),
}

TASK_CLAIM_TIER: dict[str, str] = {
    **{task_id: "IMPLEMENTATION_ONLY" for task_id, _, _, _ in TASK_CATALOG},
    **{task_id: "COORDINATION_ONLY" for task_id in ("B00", "B04", "B01", "B02", "B03")},
    **{
        task_id: "QUALIFICATION_REQUIRED"
        for task_id in (
            "X00",
            "X01",
            "X02",
            "E05",
            "H03",
            "G03",
            "P03",
            "F04",
            "C05",
            "X03",
            "X04",
            "F05",
            "R00",
        )
    },
    "R10": "GOVERNANCE_OPERATION",
    "R11": "GOVERNANCE_OPERATION",
    **{
        task_id: "RELEASE_OPERATION"
        for task_id in ("R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09")
    },
}

DEFECT_TRACEABILITY: dict[str, tuple[str, ...]] = {
    "D01": ("N02", "E02", "C01"),
    "D02": ("N02", "G01", "G02", "P01"),
    "D03": ("N03", "E03", "C03", "G02", "P01"),
    "D04": ("N01", "N07", "N08", "X01"),
    "D05": ("N02", "N04", "N08", "F02"),
    "D06": ("N04", "N06", "F04"),
    "D07": ("N03", "C02", "C05", "X02"),
    "D08": ("N03", "E04", "H02", "C02", "X02"),
    "D09": ("B03", "G01", "C03", "N10"),
    "D10": ("C01", "C02", "C05", "F03"),
    "D11": ("E05", "P02", "P03"),
    "D12": ("F01", "F02", "F03"),
    "D13": ("B03", "N09", "X04", "R05"),
    "D14": ("N07", "N08", "N10"),
    "D15": ("N03", "E04", "H02", "C02"),
    "D16": ("N04", "N06", "F04"),
    "D17": ("B01", "R01", "R02"),
}

DEFECT_CLOSURE_RULES: dict[str, str] = {
    "D01": "Close only when distinct typed simulation and plant vectors plus live role tests pass.",
    "D02": "Close only when attach, grant, revoke, and observer non-authority negatives pass with authenticated principals.",
    "D03": "Close only when declare, retire, exhaustion, restart vectors, and live stream traces pass.",
    "D04": "Close only when generated identity projections and independent exact-match and rejection results agree.",
    "D05": "Close only when transcript-swap negatives and model-to-Rust refinement pass.",
    "D06": "Close only when per-message actor and route provenance plus live rotation and revocation pass.",
    "D07": "Close only when body-issued dispositions, query and replay tests, and composed live traces pass.",
    "D08": "Close only when acquire, conflict, transfer, expiry, restart, and multi-writer campaigns pass.",
    "D09": "Close only when the extension route is registered and disjoint, core-route rejection passes, and visuals are corrected.",
    "D10": "Close only when the bypass is deleted and malformed and wrong-context ESTOP mutants fail at the latch boundary.",
    "D11": "Close only when missingness mapping and independent statistical and scientific claim review pass.",
    "D12": "Close only when bounded models, witnesses, refinement, and mutation evidence are retained and reviewed.",
    "D13": "Close only when names are owned, clean installs and advisory resolution pass, and SBOM and publication receipts exist.",
    "D14": "Close only when current surfaces are regenerated and frozen 0.8 byte identity remains unchanged.",
    "D15": "Close only when body-issued authority lifecycle and live distributed transition evidence pass.",
    "D16": "Close only when semantic public-trust projection and live rebind and revoke tests pass.",
    "D17": "Close only when release identity is accepted and external exact-subject authorization passes.",
}


def _fail(message: str) -> NoReturn:
    raise LedgerError(message)


def _exact_keys(value: dict[str, Any], expected: set[str], path: str) -> None:
    actual = set(value)
    if actual != expected:
        _fail(
            f"{path} keys differ: missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
        )


def _string(
    value: Any, path: str, *, maximum: int = 4096, nonempty: bool = True
) -> str:
    if not isinstance(value, str):
        _fail(f"{path} must be a string")
    if nonempty and not value.strip():
        _fail(f"{path} must be nonempty")
    if len(value.encode("utf-8")) > maximum:
        _fail(f"{path} exceeds {maximum} UTF-8 bytes")
    return value


def _relative_path(value: Any, path: str) -> str:
    text = _string(value, path, maximum=512)
    if not RELATIVE_PATH.fullmatch(text):
        _fail(f"{path} must be a bounded repository-relative path")
    return text


def _hex(value: Any, pattern: re.Pattern[str], path: str) -> str:
    text = _string(value, path, maximum=64)
    if not pattern.fullmatch(text):
        _fail(f"{path} has an invalid immutable digest or commit")
    return text


def _integer(value: Any, path: str, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        _fail(f"{path} must be an integer")
    if minimum is not None and value < minimum:
        _fail(f"{path} must be at least {minimum}")
    return value


def _walk_limits(value: Any, *, depth: int = 0, nodes: list[int] | None = None) -> None:
    if nodes is None:
        nodes = [0]
    nodes[0] += 1
    if nodes[0] > 100_000:
        _fail("ledger exceeds the aggregate node limit")
    if depth > 32:
        _fail("ledger exceeds the nesting-depth limit")
    if isinstance(value, dict):
        if len(value) > 256:
            _fail("ledger object exceeds 256 members")
        for key, child in value.items():
            _string(key, "object key", maximum=128)
            _walk_limits(child, depth=depth + 1, nodes=nodes)
    elif isinstance(value, list):
        if len(value) > 4096:
            _fail("ledger array exceeds 4096 items")
        for child in value:
            _walk_limits(child, depth=depth + 1, nodes=nodes)
    elif isinstance(value, str):
        _string(value, "string value", maximum=4096, nonempty=False)
    elif value is not None and not isinstance(value, (bool, int)):
        _fail(
            "ledger supports only JSON null, boolean, integer, string, array, and object values"
        )


def _scan_sensitive(value: Any, path: str = "$") -> None:
    if isinstance(value, str):
        if SECRET.search(value):
            _fail(f"{path} appears to contain a credential or private key")
        if ABSOLUTE_LOCAL_PATH.search(value):
            _fail(f"{path} contains an absolute local path")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_sensitive(child, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, child in value.items():
            _scan_sensitive(key, f"{path}.<key>")
            _scan_sensitive(child, f"{path}.{key}")


def _parse_timestamp(value: Any, path: str) -> datetime:
    text = _string(value, path, maximum=20)
    if not TIMESTAMP.fullmatch(text):
        _fail(f"{path} must be second-resolution UTC")
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise LedgerError(f"{path} is not a real UTC datetime") from error


def _check_acyclic(dependencies: dict[str, tuple[str, ...]]) -> None:
    temporary: set[str] = set()
    permanent: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in permanent:
            return
        if task_id in temporary:
            _fail(f"task dependency cycle includes {task_id}")
        temporary.add(task_id)
        for dependency in dependencies[task_id]:
            visit(dependency)
        temporary.remove(task_id)
        permanent.add(task_id)

    for task_id in dependencies:
        visit(task_id)


def _validate_review_independence(
    reviewers: list[dict[str, Any]], path: str, *, minimum: int = 1
) -> None:
    independent = [
        reviewer for reviewer in reviewers if reviewer.get("independent") is True
    ]
    identities = {reviewer.get("identity") for reviewer in independent}
    if len(identities) < minimum:
        _fail(
            f"{path} requires at least {minimum} distinct independent reviewer identities"
        )
    for reviewer in independent:
        if reviewer.get("identity") == reviewer.get("implementation_owner"):
            _fail(f"{path} cannot count self-review as independent review")


def _validate_reviewer(reviewer: Any, path: str) -> None:
    if not isinstance(reviewer, dict):
        _fail(f"{path} must be an object")
    _exact_keys(
        reviewer,
        {"identity", "role", "independent", "implementation_owner", "decision"},
        path,
    )
    for field in ("identity", "role", "implementation_owner", "decision"):
        _string(reviewer[field], f"{path}.{field}", maximum=256)
    if not isinstance(reviewer["independent"], bool):
        _fail(f"{path}.independent must be boolean")


def _validate_toolchain(toolchain: Any, path: str) -> None:
    if not isinstance(toolchain, list) or not toolchain or len(toolchain) > 32:
        _fail(f"{path} must retain between 1 and 32 tool versions")
    names: set[str] = set()
    for index, tool in enumerate(toolchain):
        tool_path = f"{path}[{index}]"
        if not isinstance(tool, dict):
            _fail(f"{tool_path} must be an object")
        _exact_keys(tool, {"name", "version"}, tool_path)
        name = _string(tool["name"], f"{tool_path}.name", maximum=64)
        _string(tool["version"], f"{tool_path}.version", maximum=256)
        if name in names:
            _fail(f"{path} duplicates tool name {name}")
        names.add(name)


def _validate_artifacts(
    artifacts: Any, path: str, *, budget: dict[str, int] | None = None
) -> list[dict[str, Any]]:
    if not isinstance(artifacts, list) or len(artifacts) > MAX_EVIDENCE_FILES:
        _fail(f"{path} must be an array of at most {MAX_EVIDENCE_FILES} artifacts")
    if budget is None:
        budget = {"references": 0, "bytes": 0}
    subjects: set[str] = set()
    relative_paths: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, artifact in enumerate(artifacts):
        artifact_path = f"{path}[{index}]"
        if not isinstance(artifact, dict):
            _fail(f"{artifact_path} must be an object")
        _exact_keys(artifact, {"subject", "path", "sha256", "bytes"}, artifact_path)
        subject = _string(artifact["subject"], f"{artifact_path}.subject", maximum=128)
        if subject in subjects:
            _fail(f"{path} contains duplicate subject {subject}")
        subjects.add(subject)
        relative = _relative_path(artifact["path"], f"{artifact_path}.path")
        if relative in relative_paths:
            _fail(f"{path} contains duplicate path {relative}")
        relative_paths.add(relative)
        expected_sha = _hex(artifact["sha256"], HEX64, f"{artifact_path}.sha256")
        expected_bytes = artifact["bytes"]
        if (
            type(expected_bytes) is not int
            or not 0 <= expected_bytes <= MAX_EVIDENCE_FILE_BYTES
        ):
            _fail(f"{artifact_path}.bytes is outside the retained-evidence bound")
        budget["references"] += 1
        budget["bytes"] += expected_bytes
        if budget["references"] > MAX_EVIDENCE_REFERENCES:
            _fail("ledger exceeds the aggregate evidence-reference bound")
        if budget["bytes"] > MAX_EVIDENCE_REFERENCED_BYTES:
            _fail("ledger exceeds the aggregate referenced-evidence byte bound")
        target = ROOT / relative
        try:
            current = ROOT
            for component in Path(relative).parts:
                current = current / component
                if current.is_symlink():
                    _fail(f"{artifact_path}.path traverses a symlink")
            stat = target.stat()
        except OSError as error:
            raise LedgerError(f"{artifact_path}.path does not exist") from error
        if not target.is_file() or target.is_symlink():
            _fail(f"{artifact_path}.path must be a regular non-symlink file")
        if stat.st_size != expected_bytes:
            _fail(f"{artifact_path}.bytes does not match retained evidence")
        digest = hashlib.sha256()
        total = 0
        with target.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_EVIDENCE_FILE_BYTES:
                    _fail(f"{artifact_path}.path exceeds the evidence byte bound")
                digest.update(chunk)
        if digest.hexdigest() != expected_sha:
            _fail(f"{artifact_path}.sha256 does not match retained evidence")
        validated.append(artifact)
    return validated


def _validate_commands(
    commands: Any, path: str, artifact_paths: set[str]
) -> list[dict[str, Any]]:
    if not isinstance(commands, list) or not commands or len(commands) > 128:
        _fail(f"{path} must retain between 1 and 128 command results")
    for index, command in enumerate(commands):
        command_path = f"{path}[{index}]"
        if not isinstance(command, dict):
            _fail(f"{command_path} must be an object")
        _exact_keys(
            command,
            {"command", "exit_code", "output_artifact", "passed", "failed", "skipped"},
            command_path,
        )
        _string(command["command"], f"{command_path}.command", maximum=1024)
        _integer(command["exit_code"], f"{command_path}.exit_code")
        if command["exit_code"] != 0 or command["failed"] != 0:
            _fail(f"{command_path} is not a passing command result")
        output = _relative_path(
            command["output_artifact"], f"{command_path}.output_artifact"
        )
        if output not in artifact_paths:
            _fail(f"{command_path}.output_artifact lacks a verified artifact record")
        for field in ("passed", "failed", "skipped"):
            _integer(command[field], f"{command_path}.{field}", minimum=0)
    return commands


def _validate_coordination_receipt(
    receipt: Any, path: str, *, budget: dict[str, int]
) -> None:
    if not isinstance(receipt, dict):
        _fail(f"{path} must be a coordination receipt object")
    _exact_keys(
        receipt,
        {"kind", "source_commit", "source_tree", "evidence", "timestamp_utc"},
        path,
    )
    if receipt["kind"] != "coordination":
        _fail(f"{path}.kind must be coordination")
    _hex(receipt["source_commit"], HEX40, f"{path}.source_commit")
    _hex(receipt["source_tree"], HEX40, f"{path}.source_tree")
    evidence = _validate_artifacts(
        receipt["evidence"], f"{path}.evidence", budget=budget
    )
    if not evidence:
        _fail(f"{path}.evidence must retain the blocker or reopen basis")
    _parse_timestamp(receipt["timestamp_utc"], f"{path}.timestamp_utc")


def _validate_push_binding(
    *,
    task_id: str,
    commit: str,
    push_ref: Any,
    object_kind: Any,
    pushed_object: Any,
    path: str,
) -> None:
    ref = _string(push_ref, f"{path}.push_ref", maximum=256)
    pushed = _hex(pushed_object, HEX40, f"{path}.pushed_object")
    if object_kind == "branch":
        if not ref.startswith("refs/heads/") or pushed != commit:
            _fail(f"{path} branch push must bind the implementation commit")
    elif object_kind == "annotated_tag":
        if task_id != "R03" or not ref.startswith("refs/tags/"):
            _fail(f"{path} annotated tag evidence is allowed only for R03")
    else:
        _fail(f"{path}.push_object_kind is invalid")


def _validate_receipt(
    receipt: Any,
    path: str,
    *,
    task_id: str,
    transition_to: str,
    budget: dict[str, int],
) -> None:
    if not isinstance(receipt, dict):
        _fail(f"{path} must be an object")
    expected = {
        "kind",
        "repository",
        "branch",
        "source_commit",
        "source_tree",
        "normative_digest_before",
        "normative_digest_after",
        "commands",
        "artifacts",
        "environment",
        "toolchain",
        "reviewers",
        "external_gates_run",
        "external_gates_not_run",
        "residual_risks",
        "rollback_or_recovery",
        "commit",
        "push_remote",
        "push_ref",
        "push_object_kind",
        "pushed_object",
        "remote_verification_artifact",
        "remote_verified_at_utc",
        "dependency_receipts",
        "timestamp_utc",
    }
    _exact_keys(receipt, expected, path)
    if receipt["kind"] != "passing":
        _fail(f"{path}.kind must be passing")
    _string(receipt["repository"], f"{path}.repository", maximum=128)
    _string(receipt["branch"], f"{path}.branch", maximum=128)
    source_commit = _hex(receipt["source_commit"], HEX40, f"{path}.source_commit")
    _hex(receipt["source_tree"], HEX40, f"{path}.source_tree")
    for name in ("normative_digest_before", "normative_digest_after"):
        value = receipt[name]
        if value is not None:
            _hex(value, HEX64, f"{path}.{name}")
    artifacts = _validate_artifacts(
        receipt["artifacts"], f"{path}.artifacts", budget=budget
    )
    artifact_paths = {artifact["path"] for artifact in artifacts}
    _validate_commands(receipt["commands"], f"{path}.commands", artifact_paths)
    _string(receipt["environment"], f"{path}.environment", maximum=1024)
    _validate_toolchain(receipt["toolchain"], f"{path}.toolchain")
    reviewers = receipt["reviewers"]
    if not isinstance(reviewers, list) or not reviewers or len(reviewers) > 16:
        _fail(f"{path}.reviewers must retain between 1 and 16 decisions")
    reviewer_identities: set[str] = set()
    for index, reviewer in enumerate(reviewers):
        _validate_reviewer(reviewer, f"{path}.reviewers[{index}]")
        if reviewer["decision"] != "PASS":
            _fail(f"{path}.reviewers[{index}].decision must be PASS")
        if reviewer["identity"] in reviewer_identities:
            _fail(f"{path}.reviewers duplicates identity {reviewer['identity']}")
        reviewer_identities.add(reviewer["identity"])
    if (
        transition_to in {"INDEPENDENT_PASS", "COMPLETE"}
        and MINIMUM_TERMINAL_CLASS[task_id] == "INDEPENDENT"
    ):
        _validate_review_independence(
            reviewers,
            f"{path}.reviewers",
            minimum=INDEPENDENT_REVIEWER_MINIMUM[task_id],
        )
    for field in ("external_gates_run", "external_gates_not_run", "residual_risks"):
        values = receipt[field]
        if not isinstance(values, list):
            _fail(f"{path}.{field} must be an array")
        for index, value in enumerate(values):
            _string(value, f"{path}.{field}[{index}]", maximum=512)
        if len(values) != len(set(values)):
            _fail(f"{path}.{field} contains duplicates")
    overlap = set(receipt["external_gates_run"]) & set(
        receipt["external_gates_not_run"]
    )
    if overlap:
        _fail(
            f"{path} records external gates as both run and not run: {sorted(overlap)}"
        )
    if transition_to == "EXTERNAL_PASS":
        missing_gates = set(REQUIRED_EXTERNAL_GATES.get(task_id, ())) - set(
            receipt["external_gates_run"]
        )
        if missing_gates:
            _fail(
                f"{path}.external_gates_run lacks checked gates: {sorted(missing_gates)}"
            )
    _string(
        receipt["rollback_or_recovery"], f"{path}.rollback_or_recovery", maximum=1024
    )
    commit = _hex(receipt["commit"], HEX40, f"{path}.commit")
    if source_commit != commit:
        _fail(
            f"{path}.source_commit and commit must identify the same implementation cut"
        )
    _string(receipt["push_remote"], f"{path}.push_remote", maximum=256)
    _validate_push_binding(
        task_id=task_id,
        commit=commit,
        push_ref=receipt["push_ref"],
        object_kind=receipt["push_object_kind"],
        pushed_object=receipt["pushed_object"],
        path=path,
    )
    remote_artifact = _relative_path(
        receipt["remote_verification_artifact"],
        f"{path}.remote_verification_artifact",
    )
    if remote_artifact not in artifact_paths:
        _fail(f"{path}.remote_verification_artifact lacks a verified artifact record")
    remote_verified_at = _parse_timestamp(
        receipt["remote_verified_at_utc"], f"{path}.remote_verified_at_utc"
    )
    bindings = receipt["dependency_receipts"]
    if not isinstance(bindings, list):
        _fail(f"{path}.dependency_receipts must be an array")
    seen_dependencies: set[str] = set()
    for index, binding in enumerate(bindings):
        binding_path = f"{path}.dependency_receipts[{index}]"
        if not isinstance(binding, dict):
            _fail(f"{binding_path} must be an object")
        _exact_keys(binding, {"task_id", "receipt_sha256"}, binding_path)
        dependency = _string(binding["task_id"], f"{binding_path}.task_id", maximum=3)
        if dependency in seen_dependencies:
            _fail(f"{path}.dependency_receipts duplicates {dependency}")
        seen_dependencies.add(dependency)
        _hex(binding["receipt_sha256"], HEX64, f"{binding_path}.receipt_sha256")
    receipt_time = _parse_timestamp(receipt["timestamp_utc"], f"{path}.timestamp_utc")
    if remote_verified_at > receipt_time:
        _fail(f"{path}.remote_verified_at_utc is newer than the receipt")


def _task_reached_minimum(task: dict[str, Any]) -> bool:
    """Return whether the current task generation reached its evidence floor.

    Reopening a passing task starts a new evidence generation. Historical external
    or independent evidence must never upgrade a later local-only implementation.
    """
    reached: set[Any] = set()
    for transition in task.get("transitions", []):
        if not isinstance(transition, dict):
            continue
        if transition.get("to") == "IN_PROGRESS":
            reached.clear()
        reached.add(transition.get("to"))
    reached.add(task.get("status"))
    required = task.get("minimum_terminal_class")
    if required == "LOCAL":
        return bool(
            reached & {"LOCAL_PASS", "EXTERNAL_PASS", "INDEPENDENT_PASS", "COMPLETE"}
        )
    if required == "EXTERNAL":
        return "EXTERNAL_PASS" in reached
    if required == "INDEPENDENT":
        return "INDEPENDENT_PASS" in reached
    return False


def _receipt_sha256(receipt: dict[str, Any]) -> str:
    encoded = json.dumps(
        receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _latest_passing_receipt(task: dict[str, Any]) -> dict[str, Any] | None:
    for transition in reversed(task.get("transitions", [])):
        if transition.get("to") in {
            "LOCAL_PASS",
            "EXTERNAL_PASS",
            "INDEPENDENT_PASS",
            "COMPLETE",
        }:
            receipt = transition.get("receipt")
            return (
                receipt
                if isinstance(receipt, dict) and receipt.get("kind") == "passing"
                else None
            )
    return None


def _validate_invalidation_record(
    record: Any, path: str, *, source_task_id: str
) -> None:
    if not isinstance(record, dict):
        _fail(f"{path} must be an object")
    _exact_keys(record, {"task_id", "receipt_sha256", "reopen_correlation_id"}, path)
    task_id = _string(record["task_id"], f"{path}.task_id", maximum=3)
    if not TASK_ID.fullmatch(task_id) or task_id == source_task_id:
        _fail(f"{path}.task_id must identify a different checked task")
    _hex(record["receipt_sha256"], HEX64, f"{path}.receipt_sha256")
    _string(
        record["reopen_correlation_id"], f"{path}.reopen_correlation_id", maximum=128
    )


def _validate_task(
    task: Any,
    expected: tuple[str, str, tuple[str, ...], str],
    path: str,
    *,
    budget: dict[str, int],
) -> None:
    if not isinstance(task, dict):
        _fail(f"{path} must be an object")
    keys = {
        "id",
        "title",
        "status",
        "claim_tier",
        "minimum_terminal_class",
        "dependencies",
        "repository",
        "source_commit",
        "target_commit",
        "dirty_state_disposition",
        "changed_files",
        "requirement_ids",
        "adr_ids",
        "perspective_reviews",
        "ten_lens_reviews",
        "commands",
        "artifacts",
        "reviewers",
        "residual_risks",
        "rollback_or_recovery",
        "invalidates",
        "transitions",
        "reviewer_comment",
    }
    _exact_keys(task, keys, path)
    task_id, title, dependencies, repository = expected
    if task["id"] != task_id or not TASK_ID.fullmatch(str(task["id"])):
        _fail(f"{path}.id is unknown or out of order")
    if task["title"] != title:
        _fail(f"{path}.title differs from the checked catalog")
    if task["dependencies"] != list(dependencies):
        _fail(f"{path}.dependencies differ from the checked DAG")
    if task["repository"] != repository:
        _fail(f"{path}.repository differs from the checked catalog")
    if task["minimum_terminal_class"] != MINIMUM_TERMINAL_CLASS[task_id]:
        _fail(f"{path}.minimum_terminal_class differs from the checked evidence class")
    if task["claim_tier"] != TASK_CLAIM_TIER[task_id]:
        _fail(f"{path}.claim_tier differs from the checked claim boundary")
    status = task["status"]
    if status not in STATUSES:
        _fail(f"{path}.status is invalid")
    for field in ("source_commit", "target_commit"):
        if task[field] is not None:
            _hex(task[field], HEX40, f"{path}.{field}")
    dirty = task["dirty_state_disposition"]
    if dirty not in {
        "NOT_EVALUATED",
        "ACCEPTED_CLEAN",
        "PRESERVED_DIRTY",
        "REFUSED_DIRTY",
    }:
        _fail(f"{path}.dirty_state_disposition is invalid")
    if (
        status in {"LOCAL_PASS", "EXTERNAL_PASS", "INDEPENDENT_PASS", "COMPLETE"}
        and dirty != "ACCEPTED_CLEAN"
    ):
        _fail(f"{path} cannot pass with dirty or unevaluated evidence")
    for field in ("changed_files", "artifacts"):
        if not isinstance(task[field], list):
            _fail(f"{path}.{field} must be an array")
        for index, value in enumerate(task[field]):
            _relative_path(value, f"{path}.{field}[{index}]")
        if len(task[field]) != len(set(task[field])):
            _fail(f"{path}.{field} contains duplicates")
    for field in ("requirement_ids", "adr_ids", "residual_risks"):
        if not isinstance(task[field], list):
            _fail(f"{path}.{field} must be an array")
        for index, value in enumerate(task[field]):
            _string(value, f"{path}.{field}[{index}]", maximum=512)
        if len(task[field]) != len(set(task[field])):
            _fail(f"{path}.{field} contains duplicates")
    required_base = (
        {
            "B00-ledger-integrity",
            "B00-no-optimistic-status",
            "B00-resumption-control",
            "B00-current-generation-evidence",
            "B00-content-bound-receipts",
        }
        if task_id == "B00"
        else {f"{task_id}-acceptance"}
    )
    if not required_base.issubset(task["requirement_ids"]):
        _fail(f"{path}.requirement_ids lacks the checked task acceptance requirement")
    if task_id == "B01" and task["adr_ids"] != [
        f"ADR-{number:03d}" for number in range(1, 12)
    ]:
        _fail(f"{path}.adr_ids must bind ADR-001 through ADR-011 exactly")
    if not isinstance(task["invalidates"], list):
        _fail(f"{path}.invalidates must be an array")
    for index, record in enumerate(task["invalidates"]):
        _validate_invalidation_record(
            record, f"{path}.invalidates[{index}]", source_task_id=task_id
        )
    if len(task["invalidates"]) != len(
        {
            (
                record["task_id"],
                record["receipt_sha256"],
                record["reopen_correlation_id"],
            )
            for record in task["invalidates"]
            if isinstance(record, dict)
        }
    ):
        _fail(f"{path}.invalidates contains duplicate records")
    for review_field, expected_ids in (
        ("perspective_reviews", PERSPECTIVES),
        ("ten_lens_reviews", LENSES),
    ):
        reviews = task[review_field]
        if not isinstance(reviews, list):
            _fail(f"{path}.{review_field} must be an array")
        ids: list[str] = []
        for index, review in enumerate(reviews):
            review_path = f"{path}.{review_field}[{index}]"
            if not isinstance(review, dict):
                _fail(f"{review_path} must be an object")
            _exact_keys(
                review, {"id", "disposition", "rationale", "reviewer"}, review_path
            )
            ids.append(_string(review["id"], f"{review_path}.id", maximum=3))
            if review["disposition"] not in {
                "NOT_REVIEWED",
                "PASS",
                "FAIL",
                "NOT_APPLICABLE",
            }:
                _fail(f"{review_path}.disposition is invalid")
            _string(review["rationale"], f"{review_path}.rationale", maximum=1024)
            _string(review["reviewer"], f"{review_path}.reviewer", maximum=128)
        if len(ids) != len(set(ids)) or any(
            identifier not in expected_ids for identifier in ids
        ):
            _fail(f"{path}.{review_field} has duplicate or unknown review IDs")
        if status in {"LOCAL_PASS", "EXTERNAL_PASS", "INDEPENDENT_PASS", "COMPLETE"}:
            if tuple(ids) != expected_ids or any(
                review["disposition"] not in {"PASS", "NOT_APPLICABLE"}
                for review in reviews
            ):
                _fail(f"{path}.{review_field} is incomplete for a passing status")
    if not isinstance(task["commands"], list) or not isinstance(
        task["reviewers"], list
    ):
        _fail(f"{path}.commands and reviewers must be arrays")
    for index, reviewer in enumerate(task["reviewers"]):
        _validate_reviewer(reviewer, f"{path}.reviewers[{index}]")
    _string(task["rollback_or_recovery"], f"{path}.rollback_or_recovery", maximum=1024)
    if task["reviewer_comment"] is not None:
        _string(task["reviewer_comment"], f"{path}.reviewer_comment", maximum=2048)
    transitions = task["transitions"]
    if not isinstance(transitions, list) or len(transitions) > 128:
        _fail(f"{path}.transitions must be an array of at most 128 transitions")
    previous = "OPEN"
    previous_time: datetime | None = None
    allowed = {
        "OPEN": {"IN_PROGRESS"},
        "IN_PROGRESS": {"BLOCKED", "LOCAL_PASS"},
        "BLOCKED": {"IN_PROGRESS"},
        "LOCAL_PASS": {"EXTERNAL_PASS", "INDEPENDENT_PASS", "COMPLETE", "IN_PROGRESS"},
        "EXTERNAL_PASS": {"INDEPENDENT_PASS", "COMPLETE", "IN_PROGRESS"},
        "INDEPENDENT_PASS": {"EXTERNAL_PASS", "COMPLETE", "IN_PROGRESS"},
        "COMPLETE": {"IN_PROGRESS"},
    }
    for index, transition in enumerate(transitions):
        transition_path = f"{path}.transitions[{index}]"
        if not isinstance(transition, dict):
            _fail(f"{transition_path} must be an object")
        _exact_keys(
            transition,
            {"from", "to", "timestamp_utc", "correlation_id", "reason", "receipt"},
            transition_path,
        )
        if transition["from"] != previous or transition["to"] not in allowed[previous]:
            _fail(f"{transition_path} is not an allowed contiguous transition")
        transition_time = _parse_timestamp(
            transition["timestamp_utc"], f"{transition_path}.timestamp_utc"
        )
        prior_time = previous_time
        if prior_time is not None and transition_time <= prior_time:
            _fail(f"{transition_path}.timestamp_utc must move strictly forward")
        previous_time = transition_time
        _string(
            transition["correlation_id"],
            f"{transition_path}.correlation_id",
            maximum=128,
        )
        _string(transition["reason"], f"{transition_path}.reason", maximum=512)
        if previous == "OPEN" and transition["to"] == "IN_PROGRESS":
            if transition["receipt"] is not None:
                _fail(
                    f"{transition_path}.receipt must be null for the initial start transition"
                )
        elif transition["to"] in {"BLOCKED", "IN_PROGRESS"}:
            _validate_coordination_receipt(
                transition["receipt"],
                f"{transition_path}.receipt",
                budget=budget,
            )
            receipt_time = _parse_timestamp(
                transition["receipt"]["timestamp_utc"],
                f"{transition_path}.receipt.timestamp_utc",
            )
            if receipt_time > transition_time:
                _fail(f"{transition_path}.receipt is newer than its transition")
            if prior_time is not None and receipt_time < prior_time:
                _fail(f"{transition_path}.receipt predates the prior transition")
        else:
            _validate_receipt(
                transition["receipt"],
                f"{transition_path}.receipt",
                task_id=task_id,
                transition_to=transition["to"],
                budget=budget,
            )
            receipt_time = _parse_timestamp(
                transition["receipt"]["timestamp_utc"],
                f"{transition_path}.receipt.timestamp_utc",
            )
            if receipt_time > transition_time:
                _fail(f"{transition_path}.receipt is newer than its transition")
            if prior_time is not None and receipt_time < prior_time:
                _fail(f"{transition_path}.receipt predates the prior transition")
            if (
                transition["to"] == "EXTERNAL_PASS"
                and not transition["receipt"]["external_gates_run"]
            ):
                _fail(f"{transition_path} EXTERNAL_PASS requires named external gates")
        previous = transition["to"]
    if previous != status:
        _fail(f"{path}.status does not match its transition history")
    if status == "OPEN" and transitions:
        _fail(f"{path} OPEN task cannot have transitions")
    if status != "OPEN" and not transitions:
        _fail(f"{path} non-OPEN task requires transition history")
    if status in {"LOCAL_PASS", "EXTERNAL_PASS", "INDEPENDENT_PASS", "COMPLETE"}:
        if (
            task["source_commit"] is None
            or not task["commands"]
            or not task["artifacts"]
        ):
            _fail(
                f"{path} passing status lacks immutable source, commands, or artifacts"
            )
        latest = _latest_passing_receipt(task)
        if latest is None:
            _fail(f"{path} passing status lacks a passing receipt")
        if task["commands"] != latest["commands"]:
            _fail(f"{path}.commands differs from the current passing receipt")
        if task["artifacts"] != [artifact["path"] for artifact in latest["artifacts"]]:
            _fail(f"{path}.artifacts differs from the current passing receipt")
        if task["reviewers"] != latest["reviewers"]:
            _fail(f"{path}.reviewers differs from the current passing receipt")
        if (
            task["source_commit"] != latest["source_commit"]
            or task["target_commit"] != latest["commit"]
        ):
            _fail(
                f"{path} current commit fields differ from the current passing receipt"
            )
    elif task["commands"] or task["artifacts"] or task["reviewers"]:
        _fail(
            f"{path} non-passing current state must retain evidence only in transition receipts"
        )
    if status == "COMPLETE" and not _task_reached_minimum(task):
        _fail(f"{path} COMPLETE did not reach its required evidence class")
    if status in {"INDEPENDENT_PASS", "COMPLETE"}:
        if MINIMUM_TERMINAL_CLASS[task_id] == "INDEPENDENT":
            _validate_review_independence(
                task["reviewers"],
                f"{path}.reviewers",
                minimum=INDEPENDENT_REVIEWER_MINIMUM[task_id],
            )


def validate(data: Any) -> None:
    _walk_limits(data)
    _scan_sensitive(data)
    if not isinstance(data, dict):
        _fail("ledger root must be an object")
    root_keys = {
        "schema",
        "claim_boundary",
        "ledger_grants_release_authorization",
        "blueprint",
        "implementation_tools",
        "defect_traceability",
        "limits",
        "perspective_mapping",
        "lens_mapping",
        "toolchain",
        "repositories",
        "tasks",
    }
    _exact_keys(data, root_keys, "$")
    if data["schema"] != SCHEMA_ID:
        _fail("$.schema is invalid")
    if data["claim_boundary"] != CLAIM_BOUNDARY:
        _fail("$.claim_boundary differs from the checked non-claim boundary")
    if data["ledger_grants_release_authorization"] is not False:
        _fail("$.ledger_grants_release_authorization must remain false")
    blueprint = data["blueprint"]
    if not isinstance(blueprint, dict):
        _fail("$.blueprint must be an object")
    _exact_keys(blueprint, {"path", "sha256"}, "$.blueprint")
    if blueprint["path"] != "docs/handoff/NCP_V1_0_ECOSYSTEM_FINALIZATION_BLUEPRINT.md":
        _fail("$.blueprint.path is not canonical")
    expected_blueprint = hashlib.sha256(BLUEPRINT.read_bytes()).hexdigest()
    if blueprint["sha256"] != expected_blueprint:
        _fail("$.blueprint.sha256 is stale")
    implementation_tools = data["implementation_tools"]
    if not isinstance(implementation_tools, list) or len(implementation_tools) != 3:
        _fail(
            "$.implementation_tools must bind exactly the checker, generator, and schema"
        )
    expected_tools = (
        "scripts/check_implementation_ledger.py",
        "scripts/generate_implementation_ledger.py",
        "evidence/implementation/task-ledger.schema.v1.json",
    )
    for index, (tool, expected_path) in enumerate(
        zip(implementation_tools, expected_tools, strict=True)
    ):
        tool_path = f"$.implementation_tools[{index}]"
        if not isinstance(tool, dict):
            _fail(f"{tool_path} must be an object")
        _exact_keys(tool, {"path", "sha256"}, tool_path)
        if tool["path"] != expected_path:
            _fail(f"{tool_path}.path is not canonical")
        expected_digest = hashlib.sha256(
            (ROOT / expected_path).read_bytes()
        ).hexdigest()
        if tool["sha256"] != expected_digest:
            _fail(f"{tool_path}.sha256 is stale")
    defect_traceability = data["defect_traceability"]
    if not isinstance(defect_traceability, list) or len(defect_traceability) != len(
        DEFECT_TRACEABILITY
    ):
        _fail("$.defect_traceability must map D01-D17 exactly")
    expected_defects = list(DEFECT_TRACEABILITY)
    if [
        entry.get("id") for entry in defect_traceability if isinstance(entry, dict)
    ] != expected_defects:
        _fail("$.defect_traceability IDs are missing, duplicated, or out of order")
    for index, entry in enumerate(defect_traceability):
        entry_path = f"$.defect_traceability[{index}]"
        if not isinstance(entry, dict):
            _fail(f"{entry_path} must be an object")
        _exact_keys(entry, {"id", "task_ids", "closure_rule"}, entry_path)
        if entry["task_ids"] != list(DEFECT_TRACEABILITY[entry["id"]]):
            _fail(f"{entry_path}.task_ids differs from the checked closure map")
        if entry["closure_rule"] != DEFECT_CLOSURE_RULES[entry["id"]]:
            _fail(f"{entry_path}.closure_rule differs from the checked closure rule")
    limits = data["limits"]
    if limits != {
        "max_file_bytes": 2_000_000,
        "max_depth": 32,
        "max_tasks": 64,
        "max_string_bytes": 4096,
        "max_evidence_references": MAX_EVIDENCE_REFERENCES,
        "max_evidence_referenced_bytes": MAX_EVIDENCE_REFERENCED_BYTES,
    }:
        _fail("$.limits differs from the enforced parser limits")
    mappings = data["perspective_mapping"]
    if (
        not isinstance(mappings, list)
        or any(not isinstance(item, dict) for item in mappings)
        or [item["id"] for item in mappings] != list(PERSPECTIVES)
    ):
        _fail("$.perspective_mapping must define P1-P3 exactly in order")
    for index, mapping in enumerate(mappings):
        _exact_keys(
            mapping,
            {"id", "name", "lens_ids", "required_question"},
            f"$.perspective_mapping[{index}]",
        )
        _string(mapping["name"], f"$.perspective_mapping[{index}].name", maximum=128)
        if not isinstance(mapping["lens_ids"], list) or not mapping["lens_ids"]:
            _fail(f"$.perspective_mapping[{index}].lens_ids must be nonempty")
        if any(lens not in LENSES for lens in mapping["lens_ids"]):
            _fail(f"$.perspective_mapping[{index}].lens_ids contains an unknown lens")
        _string(
            mapping["required_question"],
            f"$.perspective_mapping[{index}].required_question",
            maximum=1024,
        )
    lens_mapping = data["lens_mapping"]
    if (
        not isinstance(lens_mapping, list)
        or any(not isinstance(item, dict) for item in lens_mapping)
        or [item["id"] for item in lens_mapping] != list(LENSES)
    ):
        _fail("$.lens_mapping must define L1-L10 exactly in order")
    old_lenses = {f"L{number:02d}" for number in range(1, 21)}
    for index, mapping in enumerate(lens_mapping):
        _exact_keys(
            mapping,
            {"id", "name", "max_effort_lenses", "stricter_rule"},
            f"$.lens_mapping[{index}]",
        )
        _string(mapping["name"], f"$.lens_mapping[{index}].name", maximum=128)
        if (
            not isinstance(mapping["max_effort_lenses"], list)
            or not mapping["max_effort_lenses"]
        ):
            _fail(f"$.lens_mapping[{index}].max_effort_lenses must be nonempty")
        if any(lens not in old_lenses for lens in mapping["max_effort_lenses"]):
            _fail(f"$.lens_mapping[{index}] contains an unknown twenty-lens ID")
        _string(
            mapping["stricter_rule"],
            f"$.lens_mapping[{index}].stricter_rule",
            maximum=1024,
        )
    mapping_digest = hashlib.sha256(
        json.dumps(
            {
                "lens_mapping": lens_mapping,
                "perspective_mapping": mappings,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    if mapping_digest != REVIEW_MAPPING_SHA256:
        _fail(
            "review mappings differ from the checked three-perspective and ten-lens rules"
        )
    _validate_toolchain(data["toolchain"], "$.toolchain")
    repositories = data["repositories"]
    if not isinstance(repositories, list) or not repositories:
        _fail("$.repositories must be nonempty")
    repo_names: set[str] = set()
    for index, repository in enumerate(repositories):
        path = f"$.repositories[{index}]"
        if not isinstance(repository, dict):
            _fail(f"{path} must be an object")
        _exact_keys(
            repository,
            {
                "name",
                "remote",
                "branch",
                "head",
                "tree",
                "dirty",
                "changed_paths",
                "intake_disposition",
            },
            path,
        )
        name = _string(repository["name"], f"{path}.name", maximum=64)
        if name in repo_names:
            _fail(f"{path}.name is duplicated")
        repo_names.add(name)
        _string(repository["remote"], f"{path}.remote", maximum=256)
        _string(repository["branch"], f"{path}.branch", maximum=128)
        _hex(repository["head"], HEX40, f"{path}.head")
        _hex(repository["tree"], HEX40, f"{path}.tree")
        if not isinstance(repository["dirty"], bool):
            _fail(f"{path}.dirty must be boolean")
        _integer(repository["changed_paths"], f"{path}.changed_paths", minimum=0)
        if repository["dirty"] != (repository["changed_paths"] > 0):
            _fail(f"{path}.dirty disagrees with changed_paths")
        _string(
            repository["intake_disposition"], f"{path}.intake_disposition", maximum=512
        )
    if tuple(repository["name"] for repository in repositories) != REPOSITORY_NAMES:
        _fail("$.repositories differs from the checked ordered ecosystem inventory")
    tasks = data["tasks"]
    if (
        not isinstance(tasks, list)
        or len(tasks) != len(TASK_CATALOG)
        or len(tasks) > limits["max_tasks"]
    ):
        _fail("$.tasks does not contain the exact bounded catalog")
    if any(not isinstance(task, dict) for task in tasks):
        _fail("$.tasks entries must be objects")
    ids = [task.get("id") for task in tasks]
    expected_ids = [task[0] for task in TASK_CATALOG]
    if ids != expected_ids or len(ids) != len(set(ids)):
        _fail("$.tasks contains duplicate, unknown, missing, or out-of-order task IDs")
    dependency_graph = {
        task_id: dependencies for task_id, _, dependencies, _ in TASK_CATALOG
    }
    _check_acyclic(dependency_graph)
    external_tasks = {
        task_id
        for task_id, minimum in MINIMUM_TERMINAL_CLASS.items()
        if minimum == "EXTERNAL"
    }
    independent_tasks = {
        task_id
        for task_id, minimum in MINIMUM_TERMINAL_CLASS.items()
        if minimum == "INDEPENDENT"
    }
    if set(REQUIRED_EXTERNAL_GATES) != external_tasks:
        _fail("checked external-gate map does not cover every external evidence floor")
    if set(INDEPENDENT_REVIEWER_MINIMUM) != independent_tasks:
        _fail("checked reviewer map does not cover every independent evidence floor")
    evidence_budget = {"references": 0, "bytes": 0}
    for index, (task, expected) in enumerate(zip(tasks, TASK_CATALOG, strict=True)):
        _validate_task(task, expected, f"$.tasks[{index}]", budget=evidence_budget)
    task_by_id = {task["id"]: task for task in tasks}
    all_correlation_ids = [
        transition["correlation_id"]
        for task in tasks
        for transition in task["transitions"]
    ]
    if len(all_correlation_ids) != len(set(all_correlation_ids)):
        _fail("transition correlation IDs must be globally unique")
    for task in tasks:
        if task["status"] in {
            "LOCAL_PASS",
            "EXTERNAL_PASS",
            "INDEPENDENT_PASS",
            "COMPLETE",
        }:
            for dependency_id in task["dependencies"]:
                dependency = task_by_id[dependency_id]
                if dependency["status"] not in {
                    "LOCAL_PASS",
                    "EXTERNAL_PASS",
                    "INDEPENDENT_PASS",
                    "COMPLETE",
                } or not _task_reached_minimum(dependency):
                    _fail(
                        f"task {task['id']} optimistically passes before dependency {dependency_id} reaches its evidence class"
                    )
            receipt = _latest_passing_receipt(task)
            assert receipt is not None
            expected_bindings = []
            for dependency_id in task["dependencies"]:
                dependency_receipt = _latest_passing_receipt(task_by_id[dependency_id])
                if dependency_receipt is None:
                    _fail(
                        f"task {task['id']} lacks passing receipt for dependency {dependency_id}"
                    )
                expected_bindings.append(
                    {
                        "task_id": dependency_id,
                        "receipt_sha256": _receipt_sha256(dependency_receipt),
                    }
                )
            if receipt["dependency_receipts"] != expected_bindings:
                _fail(
                    f"task {task['id']} passing receipt does not bind exact dependency receipts"
                )
    catalog_order = {
        task_id: index for index, (task_id, _, _, _) in enumerate(TASK_CATALOG)
    }
    children: dict[str, list[str]] = {task_id: [] for task_id in catalog_order}
    for child_id, _, dependencies, _ in TASK_CATALOG:
        for dependency_id in dependencies:
            children[dependency_id].append(child_id)

    def descendants(task_id: str) -> list[str]:
        found: set[str] = set()
        pending = list(children[task_id])
        while pending:
            child_id = pending.pop()
            if child_id in found:
                continue
            found.add(child_id)
            pending.extend(children[child_id])
        return sorted(found, key=catalog_order.__getitem__)

    def active_receipt_before(
        task: dict[str, Any], cutoff: datetime
    ) -> dict[str, Any] | None:
        active: dict[str, Any] | None = None
        state = "OPEN"
        for transition in task["transitions"]:
            transition_time = _parse_timestamp(
                transition["timestamp_utc"], "transition timestamp"
            )
            if transition_time >= cutoff:
                break
            state = transition["to"]
            if state in {"LOCAL_PASS", "EXTERNAL_PASS", "INDEPENDENT_PASS", "COMPLETE"}:
                receipt = transition["receipt"]
                active = receipt if isinstance(receipt, dict) else None
            elif state in {"IN_PROGRESS", "BLOCKED"}:
                active = None
        return (
            active
            if state in {"LOCAL_PASS", "EXTERNAL_PASS", "INDEPENDENT_PASS", "COMPLETE"}
            else None
        )

    for task in tasks:
        expected_invalidations: list[dict[str, str]] = []
        for transition in task["transitions"]:
            if (
                transition["from"]
                not in {"LOCAL_PASS", "EXTERNAL_PASS", "INDEPENDENT_PASS", "COMPLETE"}
                or transition["to"] != "IN_PROGRESS"
            ):
                continue
            reopen_time = _parse_timestamp(
                transition["timestamp_utc"], "reopen timestamp"
            )
            for descendant_id in descendants(task["id"]):
                invalidated = active_receipt_before(
                    task_by_id[descendant_id], reopen_time
                )
                if invalidated is not None:
                    expected_invalidations.append(
                        {
                            "task_id": descendant_id,
                            "receipt_sha256": _receipt_sha256(invalidated),
                            "reopen_correlation_id": transition["correlation_id"],
                        }
                    )
        if task["invalidates"] != expected_invalidations:
            _fail(
                f"task {task['id']} invalidates does not exactly bind descendant receipts invalidated by reopen"
            )
    for defect_id, task_ids in DEFECT_TRACEABILITY.items():
        for task_id in task_ids:
            if defect_id not in task_by_id[task_id]["requirement_ids"]:
                _fail(
                    f"defect {defect_id} is absent from task {task_id} requirement_ids"
                )


def load(path: Path = LEDGER) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > 2_000_000:
        _fail("ledger exceeds 2,000,000 bytes")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"ledger is not canonical UTF-8 JSON: {error}")
    validate(value)
    canonical = (
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode()
    if raw != canonical:
        _fail("ledger bytes are not canonical two-space-indented UTF-8 JSON")
    return value


def _must_fail(action: Any, label: str, expected: str) -> None:
    try:
        action()
    except LedgerError as error:
        if expected not in str(error):
            _fail(
                f"self-test mutant {label} failed for the wrong reason: "
                f"expected {expected!r}, received {str(error)!r}"
            )
        return
    _fail(f"self-test mutant unexpectedly passed: {label}")


def self_test(data: dict[str, Any]) -> None:
    """Prove the clean ledger passes and representative hostile mutations fail closed."""
    validate(copy.deepcopy(data))

    mutant = copy.deepcopy(data)
    mutant["tasks"][0]["id"] = "Z99"
    _must_fail(lambda: validate(mutant), "unknown task", "task IDs")

    mutant = copy.deepcopy(data)
    del mutant["repositories"][7]
    _must_fail(
        lambda: validate(mutant),
        "missing pid-rs inventory",
        "checked ordered ecosystem inventory",
    )

    mutant = copy.deepcopy(data)
    mutant["tasks"][1]["dependencies"] = []
    _must_fail(lambda: validate(mutant), "missing dependency", "checked DAG")
    _must_fail(
        lambda: _check_acyclic({"B00": ("B01",), "B01": ("B00",)}),
        "cycle",
        "cycle",
    )

    mutant = copy.deepcopy(data)
    mutant["tasks"][1]["dirty_state_disposition"] = "NOT_EVALUATED"
    mutant["tasks"][1]["status"] = "LOCAL_PASS"
    _must_fail(lambda: validate(mutant), "optimistic status", "dirty or unevaluated")
    historical_external = {
        "minimum_terminal_class": "EXTERNAL",
        "status": "LOCAL_PASS",
        "transitions": [
            {"to": "LOCAL_PASS"},
            {"to": "EXTERNAL_PASS"},
            {"to": "IN_PROGRESS"},
            {"to": "LOCAL_PASS"},
        ],
    }
    if _task_reached_minimum(historical_external):
        _fail(
            "self-test current-generation evidence reset unexpectedly retained an old external pass"
        )

    _must_fail(
        lambda: _validate_review_independence(
            [
                {
                    "identity": "owner",
                    "implementation_owner": "owner",
                    "independent": True,
                }
            ],
            "reviewers",
        ),
        "self review",
        "self-review",
    )

    mutant = copy.deepcopy(data)
    mutant["tasks"][0]["source_commit"] = "abc"
    _must_fail(lambda: validate(mutant), "non-40 commit", "invalid immutable")
    _must_fail(
        lambda: _hex("main", HEX40, "source_ref"), "mutable ref", "invalid immutable"
    )

    mutant = copy.deepcopy(data)
    mutant["tasks"][0]["dirty_state_disposition"] = "PRESERVED_DIRTY"
    mutant["tasks"][0]["status"] = "LOCAL_PASS"
    _must_fail(lambda: validate(mutant), "dirty pass", "dirty or unevaluated")

    command = {
        "command": "test",
        "exit_code": 0,
        "output_artifact": "evidence/implementation/missing.log",
        "passed": 1,
        "failed": 0,
        "skipped": 0,
    }
    _must_fail(
        lambda: _validate_commands([command], "commands", set()),
        "missing command output",
        "lacks a verified artifact",
    )
    failed_command = {**command, "exit_code": 1, "failed": 1}
    _must_fail(
        lambda: _validate_commands(
            [failed_command], "commands", {"evidence/implementation/missing.log"}
        ),
        "failed command promoted",
        "not a passing command",
    )

    readme = ROOT / "README.md"
    readme_artifact = {
        "subject": "duplicate",
        "path": "README.md",
        "sha256": hashlib.sha256(readme.read_bytes()).hexdigest(),
        "bytes": readme.stat().st_size,
    }
    duplicate_subject = {
        "subject": "duplicate",
        "path": "SECURITY.md",
        "sha256": "0" * 64,
        "bytes": 0,
    }
    _must_fail(
        lambda: _validate_artifacts([readme_artifact, duplicate_subject], "artifacts"),
        "duplicate artifact subject",
        "duplicate subject",
    )
    _must_fail(
        lambda: _validate_artifacts(
            [readme_artifact],
            "artifacts",
            budget={"references": MAX_EVIDENCE_REFERENCES, "bytes": 0},
        ),
        "aggregate artifact reference budget",
        "aggregate evidence-reference bound",
    )

    receipt = {
        "artifacts": [{**readme_artifact, "subject": "remote verification"}],
        "branch": "main",
        "commands": [
            {
                "command": "bounded verification command",
                "exit_code": 0,
                "failed": 0,
                "output_artifact": "README.md",
                "passed": 1,
                "skipped": 0,
            }
        ],
        "commit": "0" * 40,
        "dependency_receipts": [],
        "environment": "isolated self-test environment",
        "external_gates_not_run": [],
        "external_gates_run": ["owner-rebaseline-authorization"],
        "kind": "passing",
        "normative_digest_after": None,
        "normative_digest_before": None,
        "push_object_kind": "branch",
        "push_ref": "refs/heads/main",
        "push_remote": "origin",
        "pushed_object": "0" * 40,
        "remote_verification_artifact": "README.md",
        "remote_verified_at_utc": "2026-07-16T06:00:00Z",
        "repository": "NCP",
        "residual_risks": [],
        "reviewers": [
            {
                "decision": "PASS",
                "identity": "local-reviewer",
                "implementation_owner": "local-reviewer",
                "independent": False,
                "role": "local evidence reviewer",
            }
        ],
        "rollback_or_recovery": "Revert the tested change.",
        "source_commit": "0" * 40,
        "source_tree": "0" * 40,
        "timestamp_utc": "2026-07-16T06:00:00Z",
        "toolchain": [{"name": "self-test", "version": "1"}],
    }
    _validate_receipt(
        copy.deepcopy(receipt),
        "receipt",
        task_id="B02",
        transition_to="EXTERNAL_PASS",
        budget={"references": 0, "bytes": 0},
    )
    bad_receipt = copy.deepcopy(receipt)
    bad_receipt["external_gates_run"] = []
    _must_fail(
        lambda: _validate_receipt(
            bad_receipt,
            "receipt",
            task_id="B02",
            transition_to="EXTERNAL_PASS",
            budget={"references": 0, "bytes": 0},
        ),
        "missing checked external gate",
        "lacks checked gates",
    )
    bad_receipt = copy.deepcopy(receipt)
    bad_receipt["remote_verification_artifact"] = "SECURITY.md"
    _must_fail(
        lambda: _validate_receipt(
            bad_receipt,
            "receipt",
            task_id="B02",
            transition_to="EXTERNAL_PASS",
            budget={"references": 0, "bytes": 0},
        ),
        "unbound remote verification",
        "lacks a verified artifact record",
    )
    bad_receipt = copy.deepcopy(receipt)
    bad_receipt["toolchain"] = []
    _must_fail(
        lambda: _validate_receipt(
            bad_receipt,
            "receipt",
            task_id="B02",
            transition_to="EXTERNAL_PASS",
            budget={"references": 0, "bytes": 0},
        ),
        "missing receipt toolchain",
        "between 1 and 32 tool versions",
    )
    independent_receipt = copy.deepcopy(receipt)
    independent_receipt["reviewers"][0].update(
        identity="independent-one",
        implementation_owner="implementation-owner",
        independent=True,
    )
    _must_fail(
        lambda: _validate_receipt(
            independent_receipt,
            "receipt",
            task_id="B01",
            transition_to="INDEPENDENT_PASS",
            budget={"references": 0, "bytes": 0},
        ),
        "insufficient independent identities",
        "at least 2 distinct independent reviewer identities",
    )
    _must_fail(
        lambda: _validate_coordination_receipt(
            {
                "evidence": [],
                "kind": "coordination",
                "source_commit": "0" * 40,
                "source_tree": "0" * 40,
                "timestamp_utc": "2026-07-16T06:00:00Z",
            },
            "coordination",
            budget={"references": 0, "bytes": 0},
        ),
        "empty coordination evidence",
        "must retain the blocker or reopen basis",
    )

    mutant = copy.deepcopy(data)
    mutant["claim_boundary"] += " ghp_abcdefghijklmnopqrstuvwxyz123456"
    _must_fail(lambda: validate(mutant), "secret", "credential")
    mutant = copy.deepcopy(data)
    mutant["claim_boundary"] += " changed"
    _must_fail(
        lambda: validate(mutant), "weakened claim boundary", "non-claim boundary"
    )
    mutant = copy.deepcopy(data)
    mutant["tasks"][0]["changed_files"] = ["/Users/example/private.txt"]
    _must_fail(lambda: validate(mutant), "absolute path", "absolute local path")

    _must_fail(
        lambda: _parse_timestamp("2026-02-30T00:00:00Z", "timestamp"),
        "impossible timestamp",
        "not a real UTC datetime",
    )
    mutant = copy.deepcopy(data)
    mutant["blueprint"]["sha256"] = "0" * 64
    _must_fail(lambda: validate(mutant), "stale blueprint", "blueprint.sha256 is stale")
    mutant = copy.deepcopy(data)
    mutant["ledger_grants_release_authorization"] = True
    _must_fail(lambda: validate(mutant), "release authorization", "must remain false")
    mutant = copy.deepcopy(data)
    mutant["implementation_tools"][0]["sha256"] = "0" * 64
    _must_fail(
        lambda: validate(mutant),
        "stale checker",
        "implementation_tools[0].sha256 is stale",
    )
    mutant = copy.deepcopy(data)
    mutant["defect_traceability"][0]["closure_rule"] = "Close from prose."
    _must_fail(
        lambda: validate(mutant), "weakened defect closure", "checked closure rule"
    )
    mutant = copy.deepcopy(data)
    mutant["perspective_mapping"][0]["name"] += " changed"
    _must_fail(
        lambda: validate(mutant), "weakened review mapping", "review mappings differ"
    )
    mutant = copy.deepcopy(data)
    mutant["tasks"][0]["claim_tier"] = "RELEASE_OPERATION"
    _must_fail(
        lambda: validate(mutant), "promoted claim tier", "checked claim boundary"
    )
    mutant = copy.deepcopy(data)
    mutant["tasks"][1]["requirement_ids"] = []
    _must_fail(
        lambda: validate(mutant), "missing task acceptance", "acceptance requirement"
    )

    nested: Any = "leaf"
    for _ in range(34):
        nested = [nested]
    _must_fail(lambda: _walk_limits(nested), "nesting bomb", "nesting-depth limit")
    _must_fail(
        lambda: _walk_limits("x" * 4097),
        "oversize string",
        "exceeds 4096 UTF-8 bytes",
    )
    _must_fail(
        lambda: _validate_reviewer({"identity": "reviewer"}, "reviewer"),
        "malformed reviewer",
        "keys differ",
    )
    _must_fail(
        lambda: _validate_push_binding(
            task_id="R02",
            commit="0" * 40,
            push_ref="refs/tags/v1.0.0",
            object_kind="annotated_tag",
            pushed_object="1" * 40,
            path="receipt",
        ),
        "tag outside R03",
        "allowed only for R03",
    )
    mutant = copy.deepcopy(data)
    mutant["tasks"][0]["invalidates"] = [
        {
            "task_id": "Z99",
            "receipt_sha256": "0" * 64,
            "reopen_correlation_id": "invalid-reopen",
        }
    ]
    _must_fail(
        lambda: validate(mutant), "unknown invalidation", "different checked task"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        data = load()
        if args.self_test:
            self_test(data)
            print(
                f"OK implementation ledger self-test: {len(TASK_CATALOG)} tasks, hostile mutants rejected"
            )
        else:
            print(
                f"OK implementation ledger: {len(TASK_CATALOG)} exact tasks; ledger_grants_release_authorization=false"
            )
        return 0
    except (OSError, LedgerError) as error:
        print(f"ERROR implementation ledger: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
